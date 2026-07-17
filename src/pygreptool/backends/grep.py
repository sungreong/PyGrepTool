from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from ..core import SearchBackendError, SearchResult
from .python import compile_pattern


def grep_available() -> bool:
    """Return True when a grep executable is available."""

    return shutil.which("grep") is not None


def _build_grep_command(
    pattern: str,
    roots: Sequence[Path],
    *,
    regex: bool,
    include: Sequence[str] | None,
    ignore_case: bool,
) -> list[str]:
    command = [
        "grep",
        "-R",
        "-n",
        "-H",
        "-I",
        "-Z",
        "--color=never",
    ]

    if ignore_case:
        command.append("-i")

    if regex:
        command.append("-E")
    else:
        command.append("-F")

    if include:
        for pattern_glob in include:
            command.append(f"--include={pattern_glob}")

    command.extend(["--", pattern])
    command.extend(str(root) for root in roots)
    return command


def _safe_compile_for_columns(pattern: str, *, regex: bool, ignore_case: bool) -> re.Pattern[str] | None:
    try:
        return compile_pattern(pattern, regex=regex, ignore_case=ignore_case)
    except re.error:
        return None


def _parse_grep_stdout(
    data: bytes,
    *,
    compiled: re.Pattern[str] | None,
    encoding: str,
) -> list[SearchResult]:
    results: list[SearchResult] = []
    index = 0

    while index < len(data):
        nul_index = data.find(b"\0", index)
        if nul_index == -1:
            break

        path_bytes = data[index:nul_index]
        line_end = data.find(b"\n", nul_index + 1)
        if line_end == -1:
            line_end = len(data)

        payload = data[nul_index + 1 : line_end]
        index = line_end + 1

        if b":" not in payload:
            continue

        line_number_bytes, line_bytes = payload.split(b":", 1)

        try:
            line_number = int(line_number_bytes.decode("ascii"))
        except ValueError:
            continue

        path = Path(os.fsdecode(path_bytes))
        line = line_bytes.decode(encoding, errors="replace").rstrip("\r\n")

        if compiled is None:
            results.append(
                SearchResult(
                    path=path,
                    line_number=line_number,
                    column=None,
                    line=line,
                    match=None,
                    backend="grep",
                )
            )
            continue

        matches = list(compiled.finditer(line))
        if not matches:
            results.append(
                SearchResult(
                    path=path,
                    line_number=line_number,
                    column=None,
                    line=line,
                    match=None,
                    backend="grep",
                )
            )
            continue

        for match in matches:
            results.append(
                SearchResult(
                    path=path,
                    line_number=line_number,
                    column=match.start() + 1,
                    line=line,
                    match=match.group(0),
                    backend="grep",
                )
            )

    return results


def search_with_grep(
    pattern: str,
    roots: Sequence[Path],
    *,
    regex: bool = True,
    include: Sequence[str] | None = None,
    ignore_case: bool = False,
    encoding: str = "utf-8",
) -> list[SearchResult]:
    """Search with grep and normalize line-oriented output.

    This backend is intentionally simpler than the ripgrep backend. It uses grep
    to find candidate lines, then Python regex is used to calculate columns when
    possible.
    """

    command = _build_grep_command(
        pattern,
        roots,
        regex=regex,
        include=include,
        ignore_case=ignore_case,
    )

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    # grep exit codes: 0 = match, 1 = no match, 2 = error.
    if process.returncode == 1:
        return []
    if process.returncode != 0:
        stderr = process.stderr.decode(encoding, errors="replace").strip()
        raise SearchBackendError(stderr or "grep failed")

    compiled = _safe_compile_for_columns(pattern, regex=regex, ignore_case=ignore_case)
    return _parse_grep_stdout(process.stdout, compiled=compiled, encoding=encoding)
