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


def _default_branch(local_dir: str) -> str:
    """Resolves the repo's default branch so feature branches fork from it,
    not from whatever branch a previous run left checked out."""
    head = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=local_dir, capture_output=True, text=True,
    )
    if head.returncode == 0 and head.stdout.strip():
        return head.stdout.strip().rsplit("/", 1)[-1]
    for cand in ("main", "master"):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", cand],
            cwd=local_dir, capture_output=True, text=True,
        )
        if check.returncode == 0:
            return cand
    return "main"


async def execute(arguments: dict) -> list[TextContent]:
    local_dir = os.path.abspath(arguments["local_dir"])
    branch_name = arguments["branch_name"]

    # Fork from the up-to-date default branch (best effort) so we never stack a
    # new feature branch on stale commits from a prior run.
    base = _default_branch(local_dir)
    subprocess.run(["git", "checkout", base], cwd=local_dir, capture_output=True, text=True)
    subprocess.run(["git", "pull", "--ff-only"], cwd=local_dir, capture_output=True, text=True)

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

    msg = result.stdout.strip() or result.stderr.strip() or f"On branch {branch_name} (from {base})"
    return [TextContent(type="text", text=msg)]
