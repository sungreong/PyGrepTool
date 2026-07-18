"""Agent-safe serialization for tool failures."""

from __future__ import annotations

from .path_policy import VirtualPathError
from .runtime_scope import ToolInputError
from .security_policy import PolicyDeniedError


_VIRTUAL_DENIAL_NEXT_STEP = (
    "Use an exact path under an existing allowed root, or ask the host to approve a narrower allowed root. "
    "Do not retry with path transformations or attempt to bypass the configured boundary."
)


def safe_tool_error_message(exc: Exception, *, virtual_mode: bool) -> str:
    """Hide host filesystem details from virtual-workspace tool responses.

    Tool errors are commonly returned to an LLM verbatim. In virtual mode, a
    detailed exception can otherwise disclose the host workspace or allowlist.
    Safe virtual-path validation messages remain useful because they contain no
    physical path information.
    """

    if not virtual_mode:
        return str(exc)
    if isinstance(exc, VirtualPathError):
        return str(exc)
    if isinstance(exc, PolicyDeniedError):
        return "access denied by policy"
    if isinstance(exc, (ToolInputError, FileNotFoundError, OSError, ValueError)):
        return "request is invalid or outside the configured virtual workspace"
    return "tool request could not run inside the configured virtual workspace"


def safe_tool_error_next_step(*, virtual_mode: bool, default: str) -> str:
    """Return agent-safe, policy-preserving recovery guidance for tool failures."""

    return _VIRTUAL_DENIAL_NEXT_STEP if virtual_mode else default
