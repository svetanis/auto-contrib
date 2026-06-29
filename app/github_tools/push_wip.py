import os
import subprocess
from mcp.types import Tool, TextContent


def get_tool() -> Tool:
    return Tool(
        name="push_wip_commit",
        description="Adds all changes, commits them, and pushes to the current branch on origin.",
        inputSchema={
            "type": "object",
            "properties": {
                "local_dir": {"type": "string", "description": "Local repository directory"},
                "commit_message": {"type": "string", "description": "Commit message"},
            },
            "required": ["local_dir", "commit_message"],
        },
    )


async def execute(arguments: dict) -> list[TextContent]:
    local_dir = os.path.abspath(arguments["local_dir"])
    msg = arguments["commit_message"]

    subprocess.run(["git", "add", "."], cwd=local_dir, capture_output=True)

    commit = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=local_dir, capture_output=True, text=True,
    )
    if commit.returncode != 0:
        err = commit.stderr.strip() or commit.stdout.strip()
        return [TextContent(type="text", text=f"Commit error: {err}")]

    push = subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=local_dir, capture_output=True, text=True,
    )
    if push.returncode != 0:
        err = push.stderr.strip() or push.stdout.strip()
        return [TextContent(type="text", text=f"Push error: {err}")]

    out = push.stderr.strip() or push.stdout.strip() or "Push successful."
    return [TextContent(type="text", text=out)]
