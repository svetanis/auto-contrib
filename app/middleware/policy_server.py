"""Policy Server — structural + semantic gating on agent tool calls.

Implements the Zero-Trust Development pattern from Day 5 white paper.
Intercepts tool calls before execution and rejects out-of-scope operations.

Gate logic (two tiers):
  Tier 1 — Structural: schema/type checks on tool arguments (fast, no LLM).
  Tier 2 — Semantic:   intent checks via keyword heuristics (can be upgraded
                        to an LLM classifier without changing the interface).
"""
import os
import re
from typing import Any

# ── Allowed scope ──────────────────────────────────────────────────────────────

# Tools the agent is always allowed to call without policy checks
_PASSTHROUGH_TOOLS = frozenset({
    "map_architecture",
    "read_file",
    "list_skills",
    "load_skill",
    "load_skill_resource",
    "search_skills",
    "poll_github_actions_logs",
})

# Destructive tools require explicit path allowlist
_WRITE_TOOLS = frozenset({
    "edit_file",
    "push_wip_commit",
    "create_feature_branch",
    "submit_pull_request",
    "sync_upstream_and_fork",
    "run_skill_script",
})

# Path prefixes the agent may write to (absolute paths from env or default)
def _allowed_write_dirs() -> list[str]:
    raw = os.environ.get("AUTOCONTRIB_ALLOWED_DIRS", "")
    if raw:
        return [p.strip() for p in raw.split(";") if p.strip()]
    return []


# ── Tier 1: Structural checks ─────────────────────────────────────────────────

def _check_structural(tool_name: str, args: dict[str, Any]) -> str | None:
    """Returns an error string if a structural constraint is violated, else None."""
    if tool_name == "edit_file":
        filepath = args.get("filepath", "")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")
        if not filepath:
            return "edit_file: 'filepath' is required."
        if not old_text:
            return "edit_file: 'old_text' must not be empty — agent must read the file first."
        if old_text == new_text:
            return "edit_file: 'old_text' and 'new_text' are identical — no change would be made."

    if tool_name == "create_feature_branch":
        branch = args.get("branch_name", "")
        if branch in ("main", "master", "develop", "release"):
            return f"create_feature_branch: cannot create branch named '{branch}' — protected branch name."

    if tool_name == "submit_pull_request":
        title = args.get("title", "")
        if not re.match(r"^(fix|feat|refactor|docs|chore|test|style|ci|build|perf)(\(.+\))?:", title):
            return (
                "submit_pull_request: PR title must follow Conventional Commits format "
                "(e.g. 'fix(auth): correct token expiry check')."
            )

    return None


# ── Tier 2: Semantic checks ───────────────────────────────────────────────────

_DANGEROUS_PATTERNS = re.compile(
    r"(rm\s+-rf|drop\s+table|delete\s+from|os\.remove|shutil\.rmtree|"
    r"subprocess\.call|eval\(|exec\(|__import__)",
    re.IGNORECASE,
)


def _check_semantic(tool_name: str, args: dict[str, Any]) -> str | None:
    """Returns an error string if a semantic constraint is violated, else None."""
    if tool_name in ("edit_file", "push_wip_commit"):
        new_text = args.get("new_text", "") or args.get("commit_message", "")
        if _DANGEROUS_PATTERNS.search(new_text):
            return (
                f"{tool_name}: proposed change contains potentially destructive code pattern. "
                "Human review required before proceeding."
            )
    return None


# ── Scope check for write operations ─────────────────────────────────────────

def _check_write_scope(tool_name: str, args: dict[str, Any]) -> str | None:
    """Verify write operations stay within allowed directories."""
    allowed = _allowed_write_dirs()
    if not allowed:
        return None  # No allowlist configured — skip check in dev

    path_arg = args.get("filepath") or args.get("local_dir") or args.get("clone_dir", "")
    if not path_arg:
        return None

    abs_path = os.path.abspath(path_arg)
    if not any(abs_path.startswith(os.path.abspath(d)) for d in allowed):
        return (
            f"{tool_name}: path '{path_arg}' is outside the allowed workspace. "
            f"Allowed dirs: {allowed}"
        )
    return None


# ── Public API ────────────────────────────────────────────────────────────────

class PolicyViolation(Exception):
    """Raised when a tool call fails the policy gate."""


def check(tool_name: str, args: dict[str, Any]) -> None:
    """Gate a tool call through structural + semantic + scope checks.

    Args:
        tool_name: The name of the tool being called.
        args: The arguments passed to the tool.

    Raises:
        PolicyViolation: If any policy check fails.
    """
    if tool_name in _PASSTHROUGH_TOOLS:
        return

    checks = [
        _check_structural(tool_name, args),
        _check_semantic(tool_name, args),
        _check_write_scope(tool_name, args) if tool_name in _WRITE_TOOLS else None,
    ]

    for result in checks:
        if result:
            raise PolicyViolation(result)


def make_before_tool_callback():
    """Returns an ADK before_tool_callback that gates all tool calls."""

    async def before_tool_callback(tool, args, tool_context):
        try:
            check(tool.name, args)
        except PolicyViolation as e:
            return {"policy_violation": str(e)}
        return None  # Allow tool to proceed

    return before_tool_callback
