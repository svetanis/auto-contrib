import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from mcp.types import Tool, TextContent

from app.middleware.context_resolver import resolve


def get_tool() -> Tool:
    return Tool(
        name="poll_github_actions_logs",
        description=(
            "Checks the latest GitHub Actions CI/CD status for a branch. "
            "Uses the GitHub REST API directly — no gh CLI required."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "local_dir": {"type": "string", "description": "Local repository directory"},
                "branch_name": {"type": "string", "description": "Branch name to check"},
            },
            "required": ["local_dir", "branch_name"],
        },
    )


async def execute(arguments: dict) -> list[TextContent]:
    local_dir = arguments["local_dir"]
    branch_name = arguments["branch_name"]

    token = (
        os.environ.get("COPILOT_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN", "")
    )
    if not token:
        return [TextContent(type="text", text="No GitHub token found (tried COPILOT_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN).")]

    remote_out = subprocess.run(
        ["git", "-C", local_dir, "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if remote_out.returncode != 0:
        return [TextContent(type="text", text=f"Error getting remote URL: {remote_out.stderr.strip()}")]

    remote_url = remote_out.stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+/[^.]+?)(?:\.git)?$", remote_url)
    if not match:
        return [TextContent(type="text", text=f"Could not parse GitHub repo from: {remote_url}")]
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
        return [TextContent(type="text", text=f"GitHub API error: {runs_data['_error']}")]

    workflow_runs = runs_data.get("workflow_runs", [])
    if not workflow_runs:
        return [TextContent(type="text", text=f"No CI/CD runs found yet for branch '{branch_name}'. Push may still be registering.")]

    run = workflow_runs[0]
    run_id = run["id"]
    status = run["status"]
    conclusion = run.get("conclusion")
    html_url = run.get("html_url", "")

    if status != "completed":
        return [TextContent(type="text", text=f"CI/CD run #{run_id} is '{status}' — still running.\nURL: {html_url}")]

    if conclusion == "success":
        return [TextContent(type="text", text=f"CI/CD PASSED on branch '{branch_name}'. All tests green!\nURL: {html_url}")]

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
    failure_text = f"CI/CD FAILED (conclusion: {conclusion})\nFailed steps:\n{summary}\nURL: {html_url}"
    # Context Hygiene: scrub any secrets/PII leaked in CI step names/logs before
    # this external text enters the LLM's context window.
    return [TextContent(type="text", text=resolve(failure_text))]
