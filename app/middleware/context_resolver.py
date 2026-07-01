"""Context Resolver — PII masking and context hygiene before the LLM sees it.

Implements the ContextResolver pattern from Day 5 white paper.
Prevents PII leakage (emails, tokens, user names) from repo issues and
commit messages into the LLM's context window.

Usage:
    from app.middleware.context_resolver import resolve

    clean_text = resolve(raw_text_from_github_issue)

The resolver replaces sensitive values with [[VARIABLE_NAME]] placeholders
that are safe to pass to the LLM. The original values are stored in a
session-scoped mapping that can be used to restore them if needed.
"""
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ── Patterns ───────────────────────────────────────────────────────────────────

_PATTERNS = [
    # GitHub/API tokens
    ("GITHUB_TOKEN",    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    # Prefix-anchored vendor key formats only — a bare {32,45} alnum run would
    # also swallow git SHAs, base64 chunks, and hashes, corrupting real content.
    ("API_KEY",         re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_\-]{16,}\b")),
    # Email addresses
    ("EMAIL",           re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")),
    # IPv4 addresses
    ("IP_ADDRESS",      re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    # Private SSH-style keys (single-line fragments)
    ("SSH_KEY",         re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL)),
    # Generic secrets (KEY=value or TOKEN=value)
    ("SECRET",          re.compile(r"\b(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)\s*=\s*\S+", re.IGNORECASE)),
]

# Fields that should NEVER be sent to the LLM even if not matching a pattern
_BLOCKED_FIELD_NAMES = frozenset({
    "password", "passwd", "pwd", "secret", "token", "api_key",
    "private_key", "client_secret", "auth", "authorization",
})


# ── Session-scoped vault ───────────────────────────────────────────────────────

@dataclass
class ResolverContext:
    """Holds the placeholder→original mapping for a single session."""
    _vault: dict[str, str] = field(default_factory=dict)

    def store(self, value: str, label: str) -> str:
        placeholder = f"[[{label}_{uuid.uuid4().hex[:6].upper()}]]"
        self._vault[placeholder] = value
        return placeholder

    def restore(self, text: str) -> str:
        for placeholder, original in self._vault.items():
            text = text.replace(placeholder, original)
        return text

    def clear(self) -> None:
        self._vault.clear()


# ── Module-level default context (single-session use) ─────────────────────────

_default_context = ResolverContext()


# ── Public API ────────────────────────────────────────────────────────────────

def resolve(text: str, ctx: Optional[ResolverContext] = None) -> str:
    """Masks PII and sensitive values in text before it reaches the LLM.

    Applies regex patterns in priority order (most specific first).
    Each matched value is replaced with a [[LABEL_XXXXXX]] placeholder.

    Args:
        text: Raw text from GitHub issues, commit messages, file contents, etc.
        ctx: Optional session-scoped context. Defaults to module-level context.

    Returns:
        Cleaned text safe to pass to the LLM.
    """
    if not text:
        return text

    ctx = ctx or _default_context

    for label, pattern in _PATTERNS:
        def _replace(match, _label=label, _ctx=ctx):
            return _ctx.store(match.group(0), _label)
        text = pattern.sub(_replace, text)

    return text


def resolve_dict(data: dict, ctx: Optional[ResolverContext] = None) -> dict:
    """Recursively masks PII in all string values of a dict.

    Blocks fields whose names match _BLOCKED_FIELD_NAMES entirely.

    Args:
        data: Dict (e.g. a GitHub API response payload).
        ctx: Optional session-scoped context.

    Returns:
        New dict with sensitive values masked.
    """
    ctx = ctx or _default_context
    result = {}
    for key, value in data.items():
        if key.lower() in _BLOCKED_FIELD_NAMES:
            result[key] = f"[[{key.upper()}_REDACTED]]"
        elif isinstance(value, str):
            result[key] = resolve(value, ctx)
        elif isinstance(value, dict):
            result[key] = resolve_dict(value, ctx)
        elif isinstance(value, list):
            result[key] = [
                resolve(item, ctx) if isinstance(item, str)
                else resolve_dict(item, ctx) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def new_context() -> ResolverContext:
    """Creates a fresh resolver context for a new session."""
    return ResolverContext()
