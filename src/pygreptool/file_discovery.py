"""Safe, high-level file discovery for coding agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .backends.python import iter_candidate_files
from .core import DEFAULT_IGNORE_FILES, PathInput, resolve_path_for_workspace, resolve_workspace_root, validate_allowed_paths


@dataclass(frozen=True)
class FileMatch:
    """A file discovered inside the configured workspace boundary."""

    path: Path
    name: str
    extension: str


def normalize_extensions(extensions: Sequence[str] | None) -> tuple[str, ...] | None:
    """Normalize ``py`` and ``.py`` to the same lowercase extension form."""

    if extensions is None:
        return None

    normalized: list[str] = []
    for extension in extensions:
        if not isinstance(extension, str):
            raise ValueError("extensions must contain strings")
        value = extension.strip().lower().lstrip(".")
        if not value or "/" in value or "\\" in value:
            raise ValueError("extensions must contain file extensions such as 'py' or '.py'")
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized) or None


def _is_within(path: Path, roots: Sequence[Path] | None) -> bool:
    if roots is None:
        return True
    return any(path == root or root in path.parents for root in roots)


def find_files(
    folder: PathInput = ".",
    *,
    name_query: str | None = None,
    extensions: Sequence[str] | None = None,
    hidden: bool = False,
    workspace_root: PathInput | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> list[FileMatch]:
    """Discover files by folder, filename text, and extensions inside an allowed scope.

    ``folder`` is resolved relative to ``workspace_root``. Every result is resolved
    before it is returned, so a symlink that exits ``allowed_roots`` is never exposed.
    """

    if not isinstance(folder, (str, Path)) or not str(folder):
        raise ValueError("folder must be a non-empty path")
    if name_query is not None and not isinstance(name_query, str):
        raise ValueError("name_query must be a string or None")

    workspace = resolve_workspace_root(workspace_root)
    resolved_folder = resolve_path_for_workspace(folder, workspace)
    resolved_allowed = (
        [resolve_path_for_workspace(root, workspace) for root in allowed_roots]
        if allowed_roots is not None
        else None
    )
    validate_allowed_paths([resolved_folder], resolved_allowed)

    normalized_extensions = normalize_extensions(extensions)
    query = name_query.casefold().strip() if name_query else None
    matches: list[FileMatch] = []
    for candidate in iter_candidate_files(
        [resolved_folder],
        hidden=hidden,
        workspace_root=workspace,
        respect_ignore=respect_ignore,
        ignore_files=ignore_files,
    ):
        resolved_candidate = candidate.resolve(strict=False)
        if not _is_within(resolved_candidate, resolved_allowed):
            continue
        extension = resolved_candidate.suffix.lower().lstrip(".")
        if normalized_extensions is not None and extension not in normalized_extensions:
            continue
        if query and query not in resolved_candidate.name.casefold():
            continue
        matches.append(FileMatch(path=resolved_candidate, name=resolved_candidate.name, extension=extension))

    return sorted(matches, key=lambda item: item.path.as_posix().casefold())
