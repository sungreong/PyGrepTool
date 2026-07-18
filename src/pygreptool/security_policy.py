"""Policy enforcement for agent access to a local code workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
import re
from typing import Callable, Literal, Sequence

from .core import PathInput

DEFAULT_DENY_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    ".git",
    ".git/**",
    "**/.git",
    "**/.git/**",
    "*.pem",
    "*.key",
    "id_rsa*",
    "credentials.yml",
    "credentials.yaml",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa*",
    "**/credentials.yml",
    "**/credentials.yaml",
)
DEFAULT_REDACTION_PATTERNS: tuple[str, ...] = (
    r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{20,}\b",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"(?i)\b(?:api[_-]?(?:key|token)|secret|token|password)\s*[:=]\s*[^\s,;]+",
)


class PolicyDeniedError(PermissionError):
    """Raised when a path is outside the agent's policy-controlled workspace."""


@dataclass(frozen=True)
class AuditEvent:
    """A host-path-free record of an agent filesystem decision."""

    tool: str
    operation: Literal["discover", "search", "read"]
    path: str
    decision: Literal["allowed", "denied"]
    reason: str | None = None


AuditSink = Callable[[AuditEvent], None]


@dataclass
class CodeAccessPolicy:
    """Enterprise-oriented read policy shared by every PyGrepTool handler.

    This is a tool-level guardrail, not a process sandbox. Pair it with a
    container/VM when untrusted code or shell access is in scope.
    """

    name: str = "repository-readonly"
    deny_globs: Sequence[str] = DEFAULT_DENY_GLOBS
    max_file_size_bytes: int = 2 * 1024 * 1024
    redaction_patterns: Sequence[str] = DEFAULT_REDACTION_PATTERNS
    audit_sink: AuditSink | None = None
    _compiled_redaction_patterns: tuple[re.Pattern[str], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_file_size_bytes < 1:
            raise ValueError("max_file_size_bytes must be positive")
        self._compiled_redaction_patterns = tuple(re.compile(pattern) for pattern in self.redaction_patterns)

    def enforce_path(self, path: Path, *, workspace_root: Path, agent_path: str, tool: str, operation: Literal["discover", "search", "read"]) -> None:
        """Allow a path only when it is in the workspace, not denied, and bounded in size."""

        try:
            relative = path.resolve(strict=False).relative_to(workspace_root.resolve(strict=False)).as_posix()
        except ValueError as exc:
            self._record(tool, operation, agent_path, "denied", "outside_workspace")
            raise PolicyDeniedError("access denied by policy") from exc

        if self._matches_denied(relative):
            self._record(tool, operation, agent_path, "denied", "deny_glob")
            raise PolicyDeniedError("access denied by policy")
        if path.is_file() and path.stat().st_size > self.max_file_size_bytes:
            self._record(tool, operation, agent_path, "denied", "file_too_large")
            raise PolicyDeniedError("access denied by policy")
        self._record(tool, operation, agent_path, "allowed")

    def allow_result_path(self, path: Path, *, workspace_root: Path) -> bool:
        """Return whether a discovered/search result may be shown to the agent."""

        try:
            relative = path.resolve(strict=False).relative_to(workspace_root.resolve(strict=False)).as_posix()
        except ValueError:
            return False
        if self._matches_denied(relative):
            return False
        try:
            return not path.is_file() or path.stat().st_size <= self.max_file_size_bytes
        except OSError:
            return False

    def redact(self, text: str) -> tuple[str, bool]:
        """Replace policy-configured secret-shaped values before tool output leaves the process."""

        redacted = text
        for pattern in self._compiled_redaction_patterns:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted, redacted != text

    def _matches_denied(self, relative_path: str) -> bool:
        name = Path(relative_path).name
        return any(fnmatch(relative_path, pattern) or fnmatch(name, pattern) for pattern in self.deny_globs)

    def _record(
        self,
        tool: str,
        operation: Literal["discover", "search", "read"],
        path: str,
        decision: Literal["allowed", "denied"],
        reason: str | None = None,
    ) -> None:
        if self.audit_sink is not None:
            self.audit_sink(AuditEvent(tool, operation, path, decision, reason))
