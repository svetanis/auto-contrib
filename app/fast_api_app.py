# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import os
import subprocess

import google.auth
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

setup_telemetry()

# Cloud Logging — optional; falls back to no-op in dev environments
try:
    _, project_id = google.auth.default()
    from google.cloud import logging as google_cloud_logging
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
    _cloud_logging = True
except Exception:
    logger = None  # type: ignore[assignment]
    _cloud_logging = False

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
session_service_uri = None
artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "auto-contrib"
app.description = "API for interacting with the Agent auto-contrib"


# ── HITL endpoints ────────────────────────────────────────────────────────────

@app.post("/api/approve")
async def approve_edit() -> dict:
    """Executes the pending edit and push — no LLM call needed."""
    from app.agent import _pending_edit, edit_file, push_wip_commit, poll_github_actions_logs

    if not _pending_edit:
        return {"status": "error", "message": "No pending edit to approve"}

    result = edit_file(
        filepath=_pending_edit["filepath"],
        old_text=_pending_edit["old_text"],
        new_text=_pending_edit["new_text"],
    )

    push_result = ""
    branch_name = ""
    local_dir = _pending_edit.get("local_dir", "")

    if local_dir and "Error" not in result:
        commit_msg = f"Fix: {_pending_edit['proposed_solution'][:80]}"
        push_result = push_wip_commit(local_dir, commit_msg)

        br = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=os.path.abspath(local_dir), capture_output=True, text=True,
        )
        branch_name = br.stdout.strip()

    cicd_status = ""
    if local_dir and branch_name and "Error" not in push_result:
        await asyncio.sleep(5)
        cicd_status = poll_github_actions_logs(local_dir, branch_name)

    return {
        "status": "approved",
        "edit_result": result,
        "push_result": push_result,
        "cicd_status": cicd_status,
        "branch_name": branch_name,
    }


@app.post("/api/reject")
async def reject_edit() -> dict:
    """Clears the pending edit without executing it."""
    from app import agent
    agent._pending_edit = {}
    return {"status": "rejected"}


# ── Feedback endpoint ─────────────────────────────────────────────────────────

@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback."""
    if _cloud_logging and logger:
        logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
