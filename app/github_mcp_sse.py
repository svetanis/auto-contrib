"""GitHub MCP server — SSE transport (FastMCP).

Exposes GitHub workflow tools over HTTP/SSE so ADK's McpToolset can
connect without stdio subprocess issues on Windows.

Start this automatically via agent.py's background thread.
Connect from ADK with:
    SseConnectionParams(url="http://127.0.0.1:8001/sse")
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("github-mcp")


@mcp.tool()
async def read_file(filepath: str) -> str:
    """Reads and returns the full contents of a file.
    Use this to inspect source code before proposing edits so you can copy old_text verbatim.

    Args:
        filepath: Absolute path to the file to read.
    """
    from app.github_tools import read_file as _mod
    results = await _mod.execute({"filepath": filepath})
    return results[0].text if results else ""


@mcp.tool()
async def create_feature_branch(local_dir: str, branch_name: str) -> str:
    """Creates a new feature branch, or checks it out if it already exists.

    Args:
        local_dir: Local repository directory.
        branch_name: Name of the new branch.
    """
    from app.github_tools import feature_branch as _mod
    results = await _mod.execute({"local_dir": local_dir, "branch_name": branch_name})
    return results[0].text if results else ""


@mcp.tool()
async def push_wip_commit(local_dir: str, commit_message: str) -> str:
    """Adds all changes, commits them, and pushes to the current branch on origin.

    Args:
        local_dir: Local repository directory.
        commit_message: Commit message.
    """
    from app.github_tools import push_wip as _mod
    results = await _mod.execute({"local_dir": local_dir, "commit_message": commit_message})
    return results[0].text if results else ""


@mcp.tool()
async def poll_github_actions_logs(local_dir: str, branch_name: str) -> str:
    """Checks the latest GitHub Actions CI/CD status for a branch via the GitHub REST API.

    Args:
        local_dir: Local repository directory.
        branch_name: Branch name to check.
    """
    from app.github_tools import poll_logs as _mod
    results = await _mod.execute({"local_dir": local_dir, "branch_name": branch_name})
    return results[0].text if results else ""


@mcp.tool()
async def submit_pull_request(
    local_dir: str,
    branch_name: str,
    title: str,
    body: str,
    base: str = "main",
) -> str:
    """Submits a Pull Request via the GitHub API. Call after CI/CD passes.
    Title must follow Conventional Commits format (e.g. 'fix(scope): message').

    Args:
        local_dir: Local repository directory.
        branch_name: Feature branch to merge from.
        title: PR title in Conventional Commits format.
        body: PR description explaining what was changed and why.
        base: Target branch (default: main).
    """
    from app.github_tools import submit_pr as _mod
    results = await _mod.execute({
        "local_dir": local_dir,
        "branch_name": branch_name,
        "title": title,
        "body": body,
        "base": base,
    })
    return results[0].text if results else ""
