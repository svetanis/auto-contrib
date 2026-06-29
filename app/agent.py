import asyncio
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.skills import load_skill_from_dir
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.tools.skill_toolset import SkillToolset
from app.middleware.policy_server import make_before_tool_callback

import google.auth

try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
except Exception:
    pass
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

AGENT_ROOT = Path(__file__).parent.parent

# ── HITL state ────────────────────────────────────────────────────────────────
# edit_file, push_wip_commit, poll_github_actions_logs and _pending_edit are
# imported by api.py's /api/approve endpoint — keep them as module-level symbols.
# They are NOT listed in root_agent.tools (agent uses MCP versions instead).

_pending_edit: dict = {}


def edit_file(filepath: str, old_text: str, new_text: str) -> str:
    """Replaces old_text with new_text in the file at filepath.

    Args:
        filepath: Absolute path to the file.
        old_text: Exact string to be replaced.
        new_text: Replacement string.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Normalize line endings so CRLF files match LF old_text from the LLM
        content = content.replace("\r\n", "\n")
        old_text = old_text.replace("\r\n", "\n")
        new_text = new_text.replace("\r\n", "\n")
        if old_text not in content:
            return "Error: old_text not found in file."
        if content.count(old_text) > 1:
            return (
                "Error: old_text occurs multiple times. Include more surrounding context "
                "(e.g., the method signature) in old_text to make it unique."
            )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.replace(old_text, new_text))
        return "File updated successfully."
    except Exception as e:
        return f"Error: {e}"


def push_wip_commit(local_dir: str, message: str) -> str:
    """Adds all changes, commits, and pushes to the current branch.

    Args:
        local_dir: Local repository directory.
        message: Commit message.
    """
    abs_dir = os.path.abspath(local_dir)
    subprocess.run(["git", "add", "."], cwd=abs_dir, capture_output=True)
    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=abs_dir, capture_output=True, text=True,
    )
    if commit.returncode != 0:
        return f"Commit error: {commit.stderr.strip() or commit.stdout.strip()}"
    push = subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=abs_dir, capture_output=True, text=True,
    )
    if push.returncode != 0:
        return f"Push error: {push.stderr.strip() or push.stdout.strip()}"
    return push.stderr.strip() or push.stdout.strip() or "Push successful."


def poll_github_actions_logs(local_dir: str, branch_name: str) -> str:
    """Checks GitHub Actions CI/CD status for the given branch via REST API.

    Args:
        local_dir: Local repository directory.
        branch_name: Branch to check.
    """
    import json
    import re
    import urllib.error
    import urllib.request

    token = (
        os.environ.get("COPILOT_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN", "")
    )
    if not token:
        return "No GitHub token found (tried COPILOT_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN)."

    remote_out = subprocess.run(
        ["git", "-C", local_dir, "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if remote_out.returncode != 0:
        return f"Error getting remote URL: {remote_out.stderr.strip()}"

    remote_url = remote_out.stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+/[^.]+?)(?:\.git)?$", remote_url)
    if not match:
        return f"Could not parse GitHub repo from: {remote_url}"
    repo = match.group(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    def api_get(url: str) -> dict:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"_error": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"_error": str(e)}

    runs_data = api_get(
        f"https://api.github.com/repos/{repo}/actions/runs?branch={branch_name}&per_page=1"
    )
    if "_error" in runs_data:
        return f"GitHub API error: {runs_data['_error']}"

    workflow_runs = runs_data.get("workflow_runs", [])
    if not workflow_runs:
        return f"No CI/CD runs found yet for branch '{branch_name}'. Push may still be registering."

    run = workflow_runs[0]
    run_id = run["id"]
    status = run["status"]
    conclusion = run.get("conclusion")
    html_url = run.get("html_url", "")

    if status != "completed":
        return f"CI/CD run #{run_id} is '{status}' — still running.\nURL: {html_url}"

    if conclusion == "success":
        return f"CI/CD PASSED on branch '{branch_name}'. All tests green!\nURL: {html_url}"

    jobs_data = api_get(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs")
    failed_steps = []
    if "jobs" in jobs_data:
        for job in jobs_data["jobs"]:
            if job.get("conclusion") not in ("success", "skipped"):
                for step in job.get("steps", []):
                    if step.get("conclusion") not in ("success", "skipped"):
                        failed_steps.append(
                            f"  Job '{job['name']}' > Step '{step['name']}': {step.get('conclusion')}"
                        )

    summary = "\n".join(failed_steps) if failed_steps else "  (see URL for full logs)"
    return f"CI/CD FAILED (conclusion: {conclusion})\nFailed steps:\n{summary}\nURL: {html_url}"


# ── HITL gate ─────────────────────────────────────────────────────────────────

def request_user_approval(
    proposed_solution: str,
    filepath: str,
    old_text: str,
    new_text: str,
    local_dir: str = "",
) -> str:
    """Pauses execution and sends the proposed code change to the user for approval.
    MUST be called before any file edit. Populate all parameters from your analysis.

    Args:
        proposed_solution: Human-readable description of the change.
        filepath: Absolute path to the file you will edit.
        old_text: Exact string to be replaced (copy verbatim from read_file output).
        new_text: Replacement string.
        local_dir: Local repository directory (for the follow-up git push).
    """
    global _pending_edit

    if not os.path.exists(filepath):
        return (
            f"Error: File not found at '{filepath}'. "
            "Use map_architecture to get the correct absolute path."
        )

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Normalize line endings to match what the LLM sends (always LF)
        if old_text.replace("\r\n", "\n") not in content.replace("\r\n", "\n"):
            return (
                f"Error: old_text not found in '{filepath}'. "
                "Re-read the file and copy the exact text to replace."
            )
    except Exception as e:
        return f"Error reading file: {e}"

    _pending_edit = {
        "filepath": filepath,
        "old_text": old_text,
        "new_text": new_text,
        "local_dir": local_dir,
        "proposed_solution": proposed_solution,
    }
    raise Exception(f"ApprovalRequired: {proposed_solution}")


# ── MCP SSE server startup ────────────────────────────────────────────────────

_MCP_STARTED = False
_GITHUB_MCP_PORT = 8001
_REPO_MAPPER_MCP_PORT = 8002


def _port_ready(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _run_sse_server(starlette_app, port: int) -> None:
    import uvicorn
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config = uvicorn.Config(starlette_app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # threads cannot install signal handlers
    loop.run_until_complete(server.serve())


def _start_mcp_servers() -> None:
    global _MCP_STARTED
    if _MCP_STARTED or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    _MCP_STARTED = True

    from app.github_mcp_sse import mcp as _github_mcp
    from app.repo_mapper_mcp_sse import mcp as _repo_mcp

    threading.Thread(
        target=_run_sse_server,
        args=(_github_mcp.sse_app(), _GITHUB_MCP_PORT),
        daemon=True,
    ).start()
    threading.Thread(
        target=_run_sse_server,
        args=(_repo_mcp.sse_app(), _REPO_MAPPER_MCP_PORT),
        daemon=True,
    ).start()

    # Wait until both ports accept connections (up to 5s each)
    _port_ready(_GITHUB_MCP_PORT)
    _port_ready(_REPO_MAPPER_MCP_PORT)


_start_mcp_servers()

# ── Instruction ───────────────────────────────────────────────────────────────

instruction = """You are auto-contrib, an autonomous GitHub coding agent.

Complete the contributor workflow step by step:

1. CALL map_architecture(local_dir) to find all source files and class/method signatures.
   The output includes %% file: <absolute_path> comments — use those paths in step 2.

2. CALL read_file(filepath) on the specific file containing the bug.
   You MUST do this before proposing any edit. Never guess at code content.

3. CALL create_feature_branch(local_dir, branch_name) to create a working branch.

4. CALL request_user_approval with ALL of these parameters:
   - proposed_solution: plain-English description of the change
   - filepath: ABSOLUTE path from step 1 (%% file: comment)
   - old_text: EXACT multi-line string from step 2, including the method signature
     (must be unique within the file)
   - new_text: corrected code, preserving all indentation
   - local_dir: the repository directory path

5. STOP after request_user_approval. The system handles the edit and push automatically.
   Do NOT call edit_file or push_wip_commit yourself.

After an approved fix has been pushed:
6. CALL poll_github_actions_logs(local_dir, branch_name) to check if tests pass.
7. If CI/CD passes, CALL submit_pull_request(local_dir, branch_name, title, body) to open the PR.

Agent Skills (use load_skill to get full instructions before starting each phase):
- architecture-mapper     — call load_skill("architecture-mapper") when mapping/visualizing repos
- code-implementer        — call load_skill("code-implementer") for TDD bug-fix workflows
- test-debugger           — call load_skill("test-debugger") to manage CI/CD polling loops
- pr-compliance-formatter — call load_skill("pr-compliance-formatter") before submitting PRs

CRITICAL RULES:
- You MUST actually call your tools. Do NOT simulate or describe what you would do.
- old_text MUST be unique within the file. Always include the surrounding method definition.
- For local_dir, use the repository path provided by the user in their prompt."""

# ── Skills ────────────────────────────────────────────────────────────────────

_skills_dir = AGENT_ROOT / "skills"
_skills = [load_skill_from_dir(_skills_dir / name) for name in [
    "architecture-mapper",
    "code-implementer",
    "test-debugger",
    "pr-compliance-formatter",
]]

# ── Agent ─────────────────────────────────────────────────────────────────────

from app.rate_limiter import RateLimitedGemini

root_agent = Agent(
    name="root_agent",
    model=RateLimitedGemini(model="gemini-2.0-flash"),
    instruction=instruction,
    before_tool_callback=make_before_tool_callback(),
    tools=[
        McpToolset(connection_params=SseConnectionParams(
            url=f"http://127.0.0.1:{_GITHUB_MCP_PORT}/sse",
        )),
        McpToolset(connection_params=SseConnectionParams(
            url=f"http://127.0.0.1:{_REPO_MAPPER_MCP_PORT}/sse",
        )),
        request_user_approval,
        SkillToolset(skills=_skills),
    ],
)

app = App(
    root_agent=root_agent,
    name="auto-contrib",
)
