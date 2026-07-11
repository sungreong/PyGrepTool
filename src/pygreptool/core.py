from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence
import os

BackendName = Literal["auto", "smart", "rg", "grep", "python"]
PathInput = str | os.PathLike[str]
RootInput = PathInput | Sequence[PathInput]
DEFAULT_IGNORE_FILES: tuple[str, ...] = (".gitignore", ".ignore")


@dataclass(frozen=True)
class ContextLine:
    """A line included as surrounding context for a search hit."""

    line_number: int
    line: str
    is_match: bool = False


@dataclass(frozen=True)
class ContextBlock:
    """A contiguous block of file context."""

    start_line: int
    end_line: int
    content: str
    lines: list[ContextLine]
    truncated: bool = False


@dataclass(frozen=True)
class SearchResult:
    """A normalized search hit.

    Attributes:
        path: File path where the hit was found.
        line_number: 1-based line number.
        column: 1-based character column. ``None`` means the backend could only
            identify the line, not the exact match column.
        line: The full line text without a trailing newline.
        match: The matched text if available.
        backend: Backend that produced this result: ``rg``, ``grep``, or ``python``.
        context: Optional surrounding context for this match.
    """

    path: Path
    line_number: int
    column: int | None
    line: str
    match: str | None = None
    backend: str = "unknown"
    context: ContextBlock | None = None


class SearchBackendError(RuntimeError):
    """Raised when a requested search backend cannot run successfully."""


def normalize_roots(root: RootInput) -> list[Path]:
    """Normalize a path or a sequence of paths into ``Path`` objects."""

    if isinstance(root, (str, os.PathLike)):
        return [Path(root)]
    return [Path(item) for item in root]


def resolve_workspace_root(workspace_root: PathInput | None) -> Path | None:
    """Resolve a workspace root when one is configured."""

    if workspace_root is None:
        return None
    return Path(workspace_root).expanduser().resolve(strict=False)


def resolve_search_roots(root: RootInput, workspace_root: PathInput | None = None) -> list[Path]:
    """Resolve search roots, making relative roots workspace-relative when configured."""

    base = resolve_workspace_root(workspace_root)
    roots = normalize_roots(root)
    if base is None:
        return roots
    return [(base / path).resolve(strict=False) if not path.is_absolute() else path.expanduser().resolve(strict=False) for path in roots]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_path_for_workspace(path: PathInput, workspace_root: PathInput | None = None) -> Path:
    """Resolve a path, treating relative paths as workspace-relative when configured."""

    candidate = Path(path).expanduser()
    base = resolve_workspace_root(workspace_root)
    if base is not None and not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=False)


def validate_allowed_paths(paths: Sequence[PathInput], allowed_roots: Sequence[PathInput] | None) -> None:
    """Validate that resolved paths are inside the resolved allowed roots."""

    if not allowed_roots:
        return

    normalized_allowed = [Path(item).expanduser().resolve(strict=False) for item in allowed_roots]
    for path in paths:
        resolved_path = Path(path).expanduser().resolve(strict=False)
        if not any(
            resolved_path == allowed or _is_relative_to(resolved_path, allowed)
            for allowed in normalized_allowed
        ):
            allowed_text = ", ".join(str(item) for item in normalized_allowed)
            raise ValueError(f"path is outside allowed_roots: {resolved_path}. allowed_roots={allowed_text}")


def _limit(results: Iterable[SearchResult], max_results: int | None) -> list[SearchResult]:
    if max_results is None:
        return list(results)
    if max_results < 0:
        raise ValueError("max_results must be None or a non-negative integer")

    limited: list[SearchResult] = []
    for item in results:
        if len(limited) >= max_results:
            break
        limited.append(item)
    return limited


def _validate_non_negative(value: int, field: str) -> None:
    if value < 0:
        raise ValueError(f"{field} must be a non-negative integer")


def _read_context_block(
    path: Path,
    *,
    line_number: int | None,
    before: int,
    after: int,
    full: bool,
    max_lines: int,
    max_chars: int,
    encoding: str,
) -> ContextBlock:
    if not path.is_file():
        raise FileNotFoundError(f"context path does not exist or is not a file: {path}")
    if not full and line_number is None:
        raise ValueError("line_number is required when full is false")
    if line_number is not None and line_number < 1:
        raise ValueError("line_number must be a positive integer")

    for field, value in {
        "before": before,
        "after": after,
        "max_lines": max_lines,
        "max_chars": max_chars,
    }.items():
        _validate_non_negative(value, field)

    if max_lines == 0 or max_chars == 0:
        return ContextBlock(start_line=1, end_line=0, content="", lines=[], truncated=True)

    start_line = 1 if full else max(1, int(line_number) - before)
    end_limit = None if full else int(line_number) + after
    lines: list[ContextLine] = []
    used_chars = 0
    truncated = False

    with path.open("r", encoding=encoding, errors="replace") as file:
        for current_line_number, raw_line in enumerate(file, start=1):
            if current_line_number < start_line:
                continue
            if end_limit is not None and current_line_number > end_limit:
                break
            if len(lines) >= max_lines:
                truncated = True
                break

            line = raw_line.rstrip("\r\n")
            remaining_chars = max_chars - used_chars
            if remaining_chars <= 0:
                truncated = True
                break
            if len(line) > remaining_chars:
                line = line[:remaining_chars]
                truncated = True

            lines.append(
                ContextLine(
                    line_number=current_line_number,
                    line=line,
                    is_match=(line_number is not None and current_line_number == line_number),
                )
            )
            used_chars += len(line)

            if truncated:
                break

    if not lines:
        return ContextBlock(start_line=start_line, end_line=start_line - 1, content="", lines=[], truncated=truncated)

    return ContextBlock(
        start_line=lines[0].line_number,
        end_line=lines[-1].line_number,
        content="\n".join(line.line for line in lines),
        lines=lines,
        truncated=truncated,
    )


def read_context(
    path: PathInput,
    *,
    line_number: int | None = None,
    before: int = 20,
    after: int = 20,
    full: bool = False,
    max_lines: int = 200,
    max_chars: int = 20000,
    workspace_root: PathInput | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
    encoding: str = "utf-8",
) -> ContextBlock:
    """Read surrounding context from a file using workspace and allowed-root policy."""

    workspace_path = resolve_workspace_root(workspace_root)
    resolved_path = resolve_path_for_workspace(path, workspace_path)
    resolved_allowed = (
        [resolve_path_for_workspace(item, workspace_path) for item in allowed_roots]
        if allowed_roots is not None
        else None
    )
    validate_allowed_paths([resolved_path], resolved_allowed)
    return _read_context_block(
        resolved_path,
        line_number=line_number,
        before=before,
        after=after,
        full=full,
        max_lines=max_lines,
        max_chars=max_chars,
        encoding=encoding,
    )


def _with_context(
    results: list[SearchResult],
    *,
    context_before: int,
    context_after: int,
    encoding: str,
) -> list[SearchResult]:
    _validate_non_negative(context_before, "context_before")
    _validate_non_negative(context_after, "context_after")
    if context_before == 0 and context_after == 0:
        return results

    with_context: list[SearchResult] = []
    for result in results:
        context = _read_context_block(
            result.path,
            line_number=result.line_number,
            before=context_before,
            after=context_after,
            full=False,
            max_lines=context_before + context_after + 1,
            max_chars=20000,
            encoding=encoding,
        )
        with_context.append(
            SearchResult(
                path=result.path,
                line_number=result.line_number,
                column=result.column,
                line=result.line,
                match=result.match,
                backend=result.backend,
                context=context,
            )
        )
    return with_context


def _finalize_results(
    results: Iterable[SearchResult],
    *,
    max_results: int | None,
    context_before: int,
    context_after: int,
    encoding: str,
) -> list[SearchResult]:
    return _with_context(
        _limit(results, max_results),
        context_before=context_before,
        context_after=context_after,
        encoding=encoding,
    )


def _should_use_python_for_smart(
    roots: Sequence[Path],
    *,
    include: Sequence[str] | None,
    hidden: bool,
    workspace_root: Path | None,
    respect_ignore: bool,
    ignore_files: Sequence[PathInput],
    file_threshold: int = 64,
) -> bool:
    """Return True when roots are small enough to avoid external process overhead."""

    from .backends.python import iter_candidate_files

    for index, _path in enumerate(
        iter_candidate_files(
            roots,
            include=include,
            hidden=hidden,
            workspace_root=workspace_root,
            respect_ignore=respect_ignore,
            ignore_files=ignore_files,
        ),
        start=1,
    ):
        if index > file_threshold:
            return False
    return True


def search(
    pattern: str,
    root: RootInput = ".",
    *,
    regex: bool = True,
    include: Sequence[str] | None = None,
    ignore_case: bool = False,
    hidden: bool = False,
    backend: BackendName = "auto",
    fallback: bool = True,
    encoding: str = "utf-8",
    max_results: int | None = None,
    workspace_root: PathInput | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
    context_before: int = 3,
    context_after: int = 3,
) -> list[SearchResult]:
    """Search files and return normalized matches.

    Args:
        pattern: Text or regex pattern to search for.
        root: File, directory, or sequence of files/directories.
        regex: If ``False``, search as a fixed string.
        include: Optional glob patterns such as ``["*.py", "*.md"]``.
        ignore_case: Case-insensitive search.
        hidden: Include hidden files/directories when the backend supports it.
        backend: ``auto``, ``smart``, ``rg``, ``grep``, or ``python``.
        fallback: In ``auto`` mode, continue to the next backend when a backend fails.
        encoding: Encoding used by the pure Python backend and grep output decoding.
        max_results: Optional cap on returned results.
        workspace_root: Base directory for relative roots and Python ignore files.
        respect_ignore: Whether the Python backend should apply configured ignore files.
        ignore_files: Ignore files to read relative to ``workspace_root`` when set, or
            relative to each searched directory otherwise.
        context_before: Number of lines to include before each match.
        context_after: Number of lines to include after each match.

    Returns:
        A list of ``SearchResult`` objects.
    """

    workspace_path = resolve_workspace_root(workspace_root)
    roots = resolve_search_roots(root, workspace_path)
    include_list = list(include) if include is not None else None
    ignore_file_list = list(ignore_files)

    if backend not in {"auto", "smart", "rg", "grep", "python"}:
        raise ValueError("backend must be one of: auto, smart, rg, grep, python")

    if backend == "rg":
        from .backends.rg import rg_available, search_with_rg

        if not rg_available():
            raise SearchBackendError("ripgrep executable 'rg' was not found")
        return _finalize_results(
            search_with_rg(
                pattern,
                roots,
                regex=regex,
                include=include_list,
                ignore_case=ignore_case,
                hidden=hidden,
            ),
            max_results=max_results,
            context_before=context_before,
            context_after=context_after,
            encoding=encoding,
        )

    if backend == "grep":
        from .backends.grep import grep_available, search_with_grep

        if not grep_available():
            raise SearchBackendError("grep executable was not found")
        return _finalize_results(
            search_with_grep(
                pattern,
                roots,
                regex=regex,
                include=include_list,
                ignore_case=ignore_case,
                encoding=encoding,
            ),
            max_results=max_results,
            context_before=context_before,
            context_after=context_after,
            encoding=encoding,
        )

    if backend == "python":
        from .backends.python import search_with_python

        return _finalize_results(
            search_with_python(
                pattern,
                roots,
                regex=regex,
                include=include_list,
                ignore_case=ignore_case,
                hidden=hidden,
                encoding=encoding,
                workspace_root=workspace_path,
                respect_ignore=respect_ignore,
                ignore_files=ignore_file_list,
            ),
            max_results=max_results,
            context_before=context_before,
            context_after=context_after,
            encoding=encoding,
        )

    if backend == "smart":
        from .backends.python import search_with_python

        if _should_use_python_for_smart(
            roots,
            include=include_list,
            hidden=hidden,
            workspace_root=workspace_path,
            respect_ignore=respect_ignore,
            ignore_files=ignore_file_list,
        ):
            return _finalize_results(
                search_with_python(
                    pattern,
                    roots,
                    regex=regex,
                    include=include_list,
                    ignore_case=ignore_case,
                    hidden=hidden,
                    encoding=encoding,
                    workspace_root=workspace_path,
                    respect_ignore=respect_ignore,
                    ignore_files=ignore_file_list,
                ),
                max_results=max_results,
                context_before=context_before,
                context_after=context_after,
                encoding=encoding,
            )

    # auto mode, and smart mode for larger roots: rg -> grep -> python
    errors: list[str] = []

    from .backends.rg import rg_available, search_with_rg

    if rg_available():
        try:
            return _finalize_results(
                search_with_rg(
                    pattern,
                    roots,
                    regex=regex,
                    include=include_list,
                    ignore_case=ignore_case,
                    hidden=hidden,
                ),
                max_results=max_results,
                context_before=context_before,
                context_after=context_after,
                encoding=encoding,
            )
        except Exception as exc:  # noqa: BLE001 - we deliberately attempt a fallback backend.
            if not fallback:
                raise
            errors.append(f"rg: {exc}")

    from .backends.grep import grep_available, search_with_grep

    if grep_available():
        try:
            return _finalize_results(
                search_with_grep(
                    pattern,
                    roots,
                    regex=regex,
                    include=include_list,
                    ignore_case=ignore_case,
                    encoding=encoding,
                ),
                max_results=max_results,
                context_before=context_before,
                context_after=context_after,
                encoding=encoding,
            )
        except Exception as exc:  # noqa: BLE001 - we deliberately attempt a fallback backend.
            if not fallback:
                raise
            errors.append(f"grep: {exc}")

    from .backends.python import search_with_python

    try:
        return _finalize_results(
            search_with_python(
                pattern,
                roots,
                regex=regex,
                include=include_list,
                ignore_case=ignore_case,
                hidden=hidden,
                encoding=encoding,
                workspace_root=workspace_path,
                respect_ignore=respect_ignore,
                ignore_files=ignore_file_list,
            ),
            max_results=max_results,
            context_before=context_before,
            context_after=context_after,
            encoding=encoding,
        )
    except Exception as exc:
        detail = "; ".join(errors) if errors else "no external backend succeeded"
        raise SearchBackendError(f"all search backends failed: {detail}; python: {exc}") from exc
