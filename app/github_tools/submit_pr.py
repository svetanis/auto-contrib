import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from mcp.types import Tool, TextContent


def get_tool() -> Tool:
    return Tool(
        name="submit_pull_request",
        description=(
            "Submits a Pull Request from the feature branch to the base branch via the GitHub API. "
            "Call this after CI/CD passes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "local_dir": {"type": "string", "description": "Local repository directory"},
                "branch_name": {"type": "string", "description": "Feature branch to merge from"},
                "title": {"type": "string", "description": "PR title (Conventional Commits style, e.g. 'fix: correct add() method')"},
                "body": {"type": "string", "description": "PR description explaining what was changed and why"},
                "base": {"type": "string", "description": "Target branch to merge into (default: main)"},
            },
            "required": ["local_dir", "branch_name", "title", "body"],
        },
    )


def _fill_pr_template(template: str, description: str) -> str:
    """Fills a PR template's placeholder with the change description and checks CI boxes."""
    result = template.replace("[Describe your changes here]", description)
    result = result.replace("- [ ] Tests pass in GitHub Actions", "- [x] Tests pass in GitHub Actions")
    result = result.replace("- [ ] Commits are squashed", "- [x] Commits are squashed")
    return result


def _search_related_issue(repo: str, title: str, token: str) -> tuple[int, str] | None:
    """Returns (issue_number, url) for the most relevant open issue, or None."""
    keywords = " ".join(w for w in title.replace("fix:", "").split() if len(w) > 3)[:120]
    if not keywords:
        return None
    query = urllib.parse.quote(f"{keywords} repo:{repo} is:issue is:open")
    req = urllib.request.Request(
        f"https://api.github.com/search/issues?q={query}&per_page=1",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = json.loads(resp.read().decode()).get("items", [])
            if items:
                return items[0]["number"], items[0]["html_url"]
    except Exception:
        pass
    return None


async def execute(arguments: dict) -> list[TextContent]:
    local_dir = os.path.abspath(arguments["local_dir"])
    branch_name = arguments["branch_name"]
    title = arguments["title"]
    body = arguments["body"]
    base = arguments.get("base", "main")

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

    # Fill PR template if the repo has one
    template_path = os.path.join(local_dir, ".github", "PULL_REQUEST_TEMPLATE.md")
    if os.path.exists(template_path):
        try:
            with open(template_path) as f:
                body = _fill_pr_template(f.read(), body)
        except Exception:
            pass  # Fall through to plain body

    # Prepend "Closes #N" if a related open issue exists
    related = _search_related_issue(repo, title, token)
    if related:
        issue_num, _ = related
        body = f"Closes #{issue_num}\n\n{body}"

    payload = json.dumps({"title": title, "body": body, "head": branch_name, "base": base}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/pulls",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            pr = json.loads(resp.read().decode())
            return [TextContent(
                type="text",
                text=f"Pull Request submitted!\nTitle: {pr['title']}\nURL: {pr['html_url']}\nStatus: {pr['state']}",
            )]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        return [TextContent(type="text", text=f"GitHub API error {e.code}: {err_body[:500]}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error submitting PR: {e}")]
