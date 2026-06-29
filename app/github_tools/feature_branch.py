import os
import subprocess
from mcp.types import Tool, TextContent


def get_tool() -> Tool:
    return Tool(
        name="create_feature_branch",
        description="Creates a new feature branch from the default branch, or checks it out if it already exists.",
        inputSchema={
            "type": "object",
            "properties": {
                "local_dir": {"type": "string", "description": "Local repository directory"},
                "branch_name": {"type": "string", "description": "Name of the new branch"},
            },
            "required": ["local_dir", "branch_name"],
        },
    )


async def execute(arguments: dict) -> list[TextContent]:
    local_dir = os.path.abspath(arguments["local_dir"])
    branch_name = arguments["branch_name"]

    result = subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=local_dir, capture_output=True, text=True,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "checkout", branch_name],
            cwd=local_dir, capture_output=True, text=True,
        )
        if result.returncode != 0:
            msg = result.stderr.strip() or result.stdout.strip()
            return [TextContent(type="text", text=f"Error: {msg}")]

    msg = result.stdout.strip() or result.stderr.strip() or f"On branch {branch_name}"
    return [TextContent(type="text", text=msg)]
