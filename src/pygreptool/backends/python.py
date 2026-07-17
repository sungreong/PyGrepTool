from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..core import DEFAULT_IGNORE_FILES, PathInput, SearchResult, resolve_workspace_root

DEFAULT_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _matches_include(path: Path, include: Sequence[str] | None) -> bool:
    if not include:
        return True

    path_text = path.as_posix()
    return any(
        fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(path_text, pattern)
        for pattern in include
    )


def _is_hidden_name(name: str) -> bool:
    return name.startswith(".") and name not in {".", ".."}


def _resolve_ignore_file(ignore_file: PathInput, *, ignore_root: Path) -> Path:
    path = Path(ignore_file).expanduser()
    if path.is_absolute():
        return path
    return ignore_root / path


def _load_ignore_spec(ignore_root: Path, *, ignore_files: Sequence[PathInput]) -> Any | None:
    try:
        from pathspec import PathSpec
    except ImportError:
        return None

    ignore_lines: list[str] = []
    for ignore_name in ignore_files:
        ignore_file = _resolve_ignore_file(ignore_name, ignore_root=ignore_root)
        if ignore_file.is_file():
            try:
                ignore_lines.extend(ignore_file.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                continue

    if not ignore_lines:
        return None

    return PathSpec.from_lines("gitignore", ignore_lines)


def _is_ignored_by_spec(path: Path, *, root: Path, ignore_spec: Any | None) -> bool:
    if ignore_spec is None:
        return False
    try:
        relative_path = path.relative_to(root).as_posix()
    except ValueError:
        return False
    return bool(ignore_spec.match_file(relative_path))


def _iter_files_from_directory(
    root: Path,
    *,
    include: Sequence[str] | None,
    hidden: bool,
    workspace_root: Path | None,
    respect_ignore: bool,
    ignore_files: Sequence[PathInput],
) -> Iterable[Path]:
    ignore_root = workspace_root or root
    ignore_spec = _load_ignore_spec(ignore_root, ignore_files=ignore_files) if respect_ignore else None
    for current_dir, dir_names, file_names in os.walk(root):
        current_path = Path(current_dir)

        dir_names[:] = [
            name
            for name in dir_names
            if name not in DEFAULT_SKIP_DIRS
            and (hidden or not _is_hidden_name(name))
            and not _is_ignored_by_spec(current_path / name, root=ignore_root, ignore_spec=ignore_spec)
        ]

        for file_name in file_names:
            if not hidden and _is_hidden_name(file_name):
                continue

            file_path = current_path / file_name
            if _is_ignored_by_spec(file_path, root=ignore_root, ignore_spec=ignore_spec):
                continue
            if _matches_include(file_path, include):
                yield file_path


def iter_candidate_files(
    roots: Sequence[Path],
    *,
    include: Sequence[str] | None = None,
    hidden: bool = False,
    workspace_root: PathInput | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> Iterable[Path]:
    """Yield candidate files from explicit files or directories."""

    seen: set[Path] = set()
    workspace_path = resolve_workspace_root(workspace_root)

    for root in roots:
        if not root.exists():
            raise FileNotFoundError(f"search root does not exist: {root}")

        if root.is_file():
            if _matches_include(root, include) and root not in seen:
                seen.add(root)
                yield root
            continue

        if root.is_dir():
            for file_path in _iter_files_from_directory(
                root,
                include=include,
                hidden=hidden,
                workspace_root=workspace_path,
                respect_ignore=respect_ignore,
                ignore_files=ignore_files,
            ):
                if file_path not in seen:
                    seen.add(file_path)
                    yield file_path
            continue

        # Ignore non-regular paths such as sockets or devices.


def is_probably_binary(path: Path, sample_size: int = 4096) -> bool:
    """Return True when a file sample contains NUL bytes."""

    try:
        with path.open("rb") as file:
            return b"\0" in file.read(sample_size)
    except OSError:
        return True


def compile_pattern(pattern: str, *, regex: bool, ignore_case: bool) -> re.Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(pattern if regex else re.escape(pattern), flags)


def search_with_python(
    pattern: str,
    roots: Sequence[Path],
    *,
    regex: bool = True,
    include: Sequence[str] | None = None,
    ignore_case: bool = False,
    hidden: bool = False,
    encoding: str = "utf-8",
    workspace_root: PathInput | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> list[SearchResult]:
    """Pure Python line-oriented search backend."""

    compiled = compile_pattern(pattern, regex=regex, ignore_case=ignore_case)
    results: list[SearchResult] = []

    for path in iter_candidate_files(
        roots,
        include=include,
        hidden=hidden,
        workspace_root=workspace_root,
        respect_ignore=respect_ignore,
        ignore_files=ignore_files,
    ):
        if is_probably_binary(path):
            continue

        try:
            with path.open("r", encoding=encoding, errors="replace") as file:
                for line_number, raw_line in enumerate(file, start=1):
                    line = raw_line.rstrip("\r\n")
                    for match in compiled.finditer(line):
                        results.append(
                            SearchResult(
                                path=path,
                                line_number=line_number,
                                column=match.start() + 1,
                                line=line,
                                match=match.group(0),
                                backend="python",
                            )
                        )
        except OSError:
            continue

    return results
