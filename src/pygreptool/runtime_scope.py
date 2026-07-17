"""Shared workspace and allowed-root resolution for read-only tool handlers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from .core import PathInput, resolve_workspace_root


class ToolInputError(ValueError):
    """Raised when tool-call arguments cannot be normalized safely."""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_path_for_tool_workspace(path: PathInput, workspace_root: Path | None) -> Path:
    """Resolve a path relative to a configured workspace when one is present."""

    candidate = Path(path).expanduser()
    if workspace_root is not None and not candidate.is_absolute():
        candidate = workspace_root / candidate
    return candidate.resolve(strict=False)


def resolve_tool_workspace_root(
    workspace_root: PathInput | None,
    allowed_roots: Sequence[PathInput] | None,
) -> tuple[Path, bool]:
    """Return the effective workspace and whether it is an explicit boundary."""

    explicit_workspace = resolve_workspace_root(workspace_root)
    if explicit_workspace is not None:
        return explicit_workspace, True

    configured_workspace = os.environ.get("PYGREPKIT_WORKSPACE_ROOT")
    if configured_workspace:
        resolved_workspace = resolve_workspace_root(configured_workspace)
        if resolved_workspace is not None:
            return resolved_workspace, True

    if allowed_roots is not None and len(allowed_roots) == 1:
        return resolve_path_for_tool_workspace(allowed_roots[0], None), False

    return Path.cwd().resolve(strict=False), False


def resolve_effective_allowed_roots(
    allowed_roots: Sequence[PathInput] | None,
    *,
    workspace_root: Path,
    default_to_workspace: bool,
) -> list[Path] | None:
    """Resolve configured allow roots, defaulting to an explicit workspace."""

    if allowed_roots is not None:
        return [resolve_path_for_tool_workspace(item, workspace_root) for item in allowed_roots]
    if default_to_workspace:
        return [workspace_root]
    return None


def validate_tool_allowed_roots(
    roots: Sequence[PathInput], allowed_roots: Sequence[PathInput] | None
) -> None:
    """Reject roots outside the configured allowlist."""

    if not allowed_roots:
        return

    normalized_allowed = [Path(item).expanduser().resolve(strict=False) for item in allowed_roots]
    for root in roots:
        resolved_root = Path(root).expanduser().resolve(strict=False)
        if not any(resolved_root == allowed or _is_relative_to(resolved_root, allowed) for allowed in normalized_allowed):
            allowed_text = ", ".join(str(item) for item in normalized_allowed)
            raise ToolInputError(f"root is outside allowed_roots: {resolved_root}. allowed_roots={allowed_text}")
