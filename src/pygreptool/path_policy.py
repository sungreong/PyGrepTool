"""Path mapping and boundary checks for agent-facing virtual paths."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re

from .core import PathInput, resolve_workspace_root


class VirtualPathError(ValueError):
    """Raised when an agent path is not valid inside the virtual workspace."""


class AgentPathMapper:
    """Map agent paths to a workspace without exposing host paths in virtual mode."""

    def __init__(self, workspace_root: PathInput, *, virtual_mode: bool = False) -> None:
        workspace = resolve_workspace_root(workspace_root)
        if workspace is None:
            raise VirtualPathError("workspace_root is required when virtual_mode is true")
        self.workspace_root = workspace
        self.virtual_mode = virtual_mode

    def to_physical(self, path: PathInput) -> Path:
        """Resolve an agent path into a host path while blocking virtual path escapes."""

        if not self.virtual_mode:
            candidate = Path(path).expanduser()
            if not candidate.is_absolute():
                candidate = self.workspace_root / candidate
            return candidate.resolve(strict=False)

        raw = str(path).strip()
        if not raw:
            raise VirtualPathError("virtual path must be non-empty")
        if "\\" in raw or re.match(r"^[A-Za-z]:", raw) or raw.startswith("//"):
            raise VirtualPathError("virtual paths must use POSIX-style paths under '/'")
        parsed = PurePosixPath(raw)
        parts = [part for part in parsed.parts if part not in {"/", "."}]
        if any(part == ".." or part.startswith("~") for part in parts):
            raise VirtualPathError("virtual paths cannot contain '..' or '~'")

        candidate = (self.workspace_root.joinpath(*parts)).resolve(strict=False)
        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise VirtualPathError("virtual path resolves outside workspace_root")
        return candidate

    def to_agent_path(self, path: PathInput) -> str:
        """Return a virtual POSIX path without leaking the host workspace path."""

        resolved = Path(path).expanduser().resolve(strict=False)
        if not self.virtual_mode:
            return str(resolved)
        try:
            relative = resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise VirtualPathError("cannot expose a path outside workspace_root") from exc
        return "/" if relative == Path(".") else "/" + relative.as_posix()
