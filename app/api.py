import os
import sys
import json
import asyncio
import subprocess
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Zero-dependency .env loader
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value.strip('"\'')

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.agent import root_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

app = FastAPI(title="auto-contrib A2UI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_service = InMemorySessionService()
_current_session_id = None  # Persisted across approve/reject cycles
_last_branch: dict = {}     # Tracks {local_dir, branch_name} after approve for PR submission

class RunRequest(BaseModel):
    prompt: str

@app.post("/api/run")
async def run_agent(req: RunRequest):
    global _current_session_id
    async def event_stream():
        global _current_session_id
        import app.agent as _agent_mod

        # Clear stale pending edit so post-loop check reflects only this run
        _agent_mod._pending_edit = {}

        # Reuse session if one exists so agent retains full history
        if _current_session_id is None:
            session = session_service.create_session_sync(user_id="web_user", app_name="auto-contrib")
            _current_session_id = session.id

        active_session_id = _current_session_id
        runner = Runner(agent=root_agent, session_service=session_service, app_name="auto-contrib")
        message = types.Content(role="user", parts=[types.Part.from_text(text=req.prompt)])

        try:
            async for event in runner.run_async(new_message=message, user_id="web_user", session_id=active_session_id):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            data = json.dumps({"text": part.text})
                            yield f"data: {data}\n\n"
                        elif part.function_call:
                            msg = f"\n[Agent] Calling tool: {part.function_call.name}({part.function_call.args})\n"
                            data = json.dumps({"text": msg})
                            yield f"data: {data}\n\n"
                        elif part.function_response:
                            msg = f"\n[Tool Output] {part.function_response.name}: {part.function_response.response}\n"
                            data = {"text": msg}
                            if part.function_response.name == "map_architecture":
                                resp_dict = part.function_response.response
                                # MCP SSE wraps result in structuredContent; direct calls use "result" key
                                mermaid_text = (
                                    (resp_dict.get("structuredContent") or {}).get("result")
                                    or resp_dict.get("result")
                                )
                                if mermaid_text:
                                    data["mermaid"] = mermaid_text
                            yield f"data: {json.dumps(data)}\n\n"

            # ADK swallows the ApprovalRequired exception internally (logs it as ERROR
            # but does not re-raise it to us). Check _pending_edit to detect HITL pause.
            if _agent_mod._pending_edit:
                payload = {
                    "approval_required": True,
                    "proposed_solution": _agent_mod._pending_edit.get("proposed_solution", ""),
                    "filepath": _agent_mod._pending_edit.get("filepath", ""),
                    "old_text": _agent_mod._pending_edit.get("old_text", ""),
                    "new_text": _agent_mod._pending_edit.get("new_text", ""),
                }
                yield f"data: {json.dumps(payload)}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'complete'})}\n\n"
        except Exception as e:
            err_str = str(e)
            if err_str.startswith("ApprovalRequired:"):
                # Fallback: some ADK versions do propagate the exception
                payload = {
                    "approval_required": True,
                    "proposed_solution": _agent_mod._pending_edit.get("proposed_solution", ""),
                    "filepath": _agent_mod._pending_edit.get("filepath", ""),
                    "old_text": _agent_mod._pending_edit.get("old_text", ""),
                    "new_text": _agent_mod._pending_edit.get("new_text", ""),
                }
                yield f"data: {json.dumps(payload)}\n\n"
            else:
                yield f"data: {json.dumps({'error': err_str})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/api/reset")
async def reset_session():
    """Clears the current session so a new task starts fresh."""
    global _current_session_id
    _current_session_id = None
    return {"status": "reset"}

@app.post("/api/approve")
async def approve_edit():
    """Executes the pending edit and push directly — no LLM call needed."""
    from app.agent import _pending_edit, edit_file, push_wip_commit, poll_github_actions_logs
    if not _pending_edit:
        return {"status": "error", "message": "No pending edit to approve"}

    # 1. Apply the file edit
    result = edit_file(
        filepath=_pending_edit["filepath"],
        old_text=_pending_edit["old_text"],
        new_text=_pending_edit["new_text"],
    )

    push_result = ""
    branch_name = ""
    local_dir = _pending_edit.get("local_dir", "")

    # 2. Push only if edit succeeded
    if local_dir and "Error" not in result:
        commit_msg = f"Fix: {_pending_edit['proposed_solution'][:80]}"
        push_result = push_wip_commit(local_dir, commit_msg)

        # Get current branch name for CI/CD polling
        br = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=os.path.abspath(local_dir), capture_output=True, text=True
        )
        branch_name = br.stdout.strip()

    # Store branch info as soon as push succeeds so /api/submit-pr is always available
    if local_dir and branch_name and "Error" not in push_result:
        _last_branch["local_dir"] = local_dir
        _last_branch["branch_name"] = branch_name
        _last_branch["proposed_solution"] = _pending_edit.get("proposed_solution", "")

    # 3. Poll CI/CD (give GitHub Actions 15 seconds to register the push)
    cicd_status = ""
    if local_dir and branch_name and "Error" not in push_result:
        await asyncio.sleep(15)
        cicd_status = poll_github_actions_logs(local_dir, branch_name)

    return {
        "status": "approved",
        "edit_result": result,
        "push_result": push_result,
        "cicd_status": cicd_status,
        "branch_name": branch_name,
        "ci_passed": cicd_status.startswith("CI/CD PASSED"),
    }

@app.post("/api/reject")
async def reject_edit():
    """Clears the pending edit without executing it."""
    from app import agent
    agent._pending_edit = {}
    return {"status": "rejected"}


class SubmitPrRequest(BaseModel):
    title: str = ""
    body: str = ""


@app.post("/api/submit-pr")
async def submit_pr_endpoint(req: SubmitPrRequest):
    """Submits a PR for the last approved branch. Title/body auto-generated if not provided."""
    if not _last_branch.get("branch_name"):
        return {"status": "error", "message": "No branch available — approve a change first."}

    local_dir = _last_branch["local_dir"]
    branch_name = _last_branch["branch_name"]
    proposed = _last_branch.get("proposed_solution", "automated fix")

    # Auto-generate Conventional Commits title if not provided
    title = req.title.strip() or f"fix: {proposed[:60].rstrip('.')}"
    body = req.body.strip() or f"Automated fix applied by auto-contrib agent.\n\n{proposed}"

    from app.github_tools import submit_pr as _mod
    results = await _mod.execute({
        "local_dir": local_dir,
        "branch_name": branch_name,
        "title": title,
        "body": body,
        "base": "main",
    })
    text = results[0].text if results else "Unknown result"
    ok = text.startswith("Pull Request submitted!")
    return {"status": "submitted" if ok else "error", "result": text}


# Serve the static files
web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
