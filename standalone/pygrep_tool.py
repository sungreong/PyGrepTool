"""Copy-paste local file search for small tools and LLM agents.

Zero dependencies.  Copy this file into a project and import ``search_files``.
The full ``pygreptool`` package adds rg/grep backends, richer ignore handling,
CLI commands, and framework integrations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, Sequence
import os
import re


SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__",
    "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


@dataclass(frozen=True)
class SearchHit:
    path: str
    line_number: int
    column: int
    line: str
    match: str
    context: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _inside(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def _files(
    roots: Sequence[Path], include: Sequence[str] | None, hidden: bool
) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            raise FileNotFoundError(f"search root does not exist: {root}")
        if root.is_file():
            candidates = [root]
        else:
            candidates = []
            for current, dirs, names in os.walk(root):
                dirs[:] = [
                    name for name in dirs
                    if name not in SKIP_DIRS and (hidden or not name.startswith("."))
                ]
                candidates.extend(Path(current) / name for name in names)

        for path in candidates:
            if path in seen or (not hidden and path.name.startswith(".")):
                continue
            relative = path.as_posix()
            if include and not any(
                fnmatch(path.name, pattern) or fnmatch(relative, pattern)
                for pattern in include
            ):
                continue
            seen.add(path)
            yield path


def _context(lines: list[str], index: int, before: int, after: int) -> str:
    start = max(0, index - before)
    end = min(len(lines), index + after + 1)
    return "\n".join(
        f"{number + 1}: {lines[number]}" for number in range(start, end)
    )


def search_files(
    pattern: str,
    roots: str | os.PathLike[str] | Sequence[str | os.PathLike[str]] = ".",
    *,
    regex: bool = False,
    include: Sequence[str] | None = None,
    ignore_case: bool = False,
    hidden: bool = False,
    max_results: int = 50,
    context_before: int = 2,
    context_after: int = 2,
    allowed_roots: Sequence[str | os.PathLike[str]] | None = None,
    encoding: str = "utf-8",
) -> list[SearchHit]:
    """Search local text files and return exact, JSON-serializable locations."""

    if max_results < 0 or context_before < 0 or context_after < 0:
        raise ValueError("result and context limits must be non-negative")
    raw_roots = [roots] if isinstance(roots, (str, os.PathLike)) else list(roots)
    search_roots = [Path(root).expanduser().resolve() for root in raw_roots]
    allowed = (
        [Path(root).expanduser().resolve() for root in allowed_roots]
        if allowed_roots is not None else None
    )
    if allowed and not all(_inside(root, allowed) for root in search_roots):
        raise ValueError("a search root is outside allowed_roots")

    flags = re.IGNORECASE if ignore_case else 0
    compiled = re.compile(pattern if regex else re.escape(pattern), flags)
    hits: list[SearchHit] = []
    if max_results == 0:
        return hits

    for path in _files(search_roots, include, hidden):
        try:
            with path.open("rb") as binary_file:
                if b"\0" in binary_file.read(4096):
                    continue
            if not path.is_file():
                continue
            lines = path.read_text(encoding=encoding, errors="replace").splitlines()
        except OSError:
            continue

        for index, line in enumerate(lines):
            for match in compiled.finditer(line):
                hits.append(SearchHit(
                    path=str(path),
                    line_number=index + 1,
                    column=match.start() + 1,
                    line=line,
                    match=match.group(0),
                    context=_context(lines, index, context_before, context_after),
                ))
                if len(hits) >= max_results:
                    return hits
    return hits


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Zero-dependency local file search")
    parser.add_argument("pattern")
    parser.add_argument("roots", nargs="*", default=["."])
    parser.add_argument("--regex", action="store_true")
    parser.add_argument("--include", action="append")
    parser.add_argument("--max-results", type=int, default=50)
    args = parser.parse_args()
    results = search_files(
        args.pattern, args.roots, regex=args.regex,
        include=args.include, max_results=args.max_results,
    )
    print(json.dumps([hit.to_dict() for hit in results], ensure_ascii=False, indent=2))
