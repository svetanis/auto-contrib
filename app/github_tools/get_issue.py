import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from mcp.types import Tool, TextContent

from app.middleware.context_resolver import resolve

# Cap how much external text we pull into the model's context.
_MAX_BODY_CHARS = 4000
_MAX_COMMENTS = 5
_MAX_COMMENT_CHARS = 1500


def get_tool() -> Tool:
    return Tool(
        name="get_github_issue",
        description=(
            "Fetches a GitHub issue's title, body, and discussion comments so you can "
            "understand the problem to solve. Call this FIRST when the user references an "
            "issue number — it tells you what is broken so you can investigate and fix it. "
            "Auto-detects the upstream repository when the local clone is a fork (issues live "
            "on the upstream repo, not the fork)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "local_dir": {"type": "string", "description": "Local repository directory"},
                "issue_number": {"type": "string", "description": "Issue number, e.g. '175'"},
                "repo": {
                    "type": "string",
                    "description": (
                        "Optional 'owner/name' override. If omitted, the repo is derived from "
                        "the local clone's origin remote (resolving to the fork's parent when "
                        "the clone is a fork)."
                    ),
                },
            },
            "required": ["local_dir", "issue_number"],
        },
    )


def _origin_repo(local_dir: str) -> tuple[str | None, str | None]:
    """Returns (owner/name, error) parsed from the origin remote."""
    remote_out = subprocess.run(
        ["git", "-C", local_dir, "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if remote_out.returncode != 0:
        return None, f"Error getting remote URL: {remote_out.stderr.strip()}"
    match = re.search(r"github\.com[:/]([^/]+/[^.]+?)(?:\.git)?$", remote_out.stdout.strip())
    if not match:
        return None, f"Could not parse GitHub repo from: {remote_out.stdout.strip()}"
    return match.group(1), None


async def execute(arguments: dict) -> list[TextContent]:
    local_dir = os.path.abspath(arguments["local_dir"])
    issue_number = re.sub(r"\D", "", str(arguments["issue_number"]))
    if not issue_number:
        return [TextContent(type="text", text="Error: issue_number must contain digits, e.g. '175'.")]
    repo_override = arguments.get("repo", "").strip()

    token = (
        os.environ.get("COPILOT_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN", "")
    )
    if not token:
        return [TextContent(type="text", text="No GitHub token found (tried COPILOT_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN).")]

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    def api_get(url: str) -> dict | list:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"_error": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"_error": str(e)}

    # Resolve which repo owns the issue.
    if repo_override:
        repo = repo_override
    else:
        repo, err = _origin_repo(local_dir)
        if err:
            return [TextContent(type="text", text=err)]
        # Forks don't carry issues — if origin is a fork, look upstream.
        meta = api_get(f"https://api.github.com/repos/{repo}")
        if isinstance(meta, dict) and meta.get("fork") and meta.get("parent", {}).get("full_name"):
            repo = meta["parent"]["full_name"]

    issue = api_get(f"https://api.github.com/repos/{repo}/issues/{issue_number}")
    if isinstance(issue, dict) and "_error" in issue:
        return [TextContent(type="text", text=f"GitHub API error fetching {repo}#{issue_number}: {issue['_error']}")]
    if not isinstance(issue, dict) or "title" not in issue:
        return [TextContent(type="text", text=f"Issue {repo}#{issue_number} not found or malformed.")]

    body = (issue.get("body") or "(no description)")[:_MAX_BODY_CHARS]
    parts = [
        f"Issue {repo}#{issue_number}: {issue['title']}",
        f"State: {issue.get('state', 'unknown')} | URL: {issue.get('html_url', '')}",
        "",
        body,
    ]

    # Comments frequently hold the actual reproduction / clarification.
    if issue.get("comments", 0):
        comments = api_get(
            f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments?per_page={_MAX_COMMENTS}"
        )
        if isinstance(comments, list) and comments:
            parts.append("\n--- Comments ---")
            for c in comments[:_MAX_COMMENTS]:
                user = c.get("user", {}).get("login", "unknown")
                text = (c.get("body") or "")[:_MAX_COMMENT_CHARS]
                parts.append(f"\n@{user}:\n{text}")

    # Context Hygiene: the issue text is external data — scrub secrets/PII before
    # it enters the LLM's context window.
    return [TextContent(type="text", text=resolve("\n".join(parts)))]
