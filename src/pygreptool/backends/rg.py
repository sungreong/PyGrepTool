from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from pygreptool.core import SearchBackendError, SearchResult


def rg_available() -> bool:
    """Return True when the ripgrep executable is available."""

    return shutil.which("rg") is not None


def _decode_json_text(value: dict[str, Any]) -> str:
    if "text" in value:
        return value["text"]
    if "bytes" in value:
        return base64.b64decode(value["bytes"]).decode("utf-8", errors="replace")
    return ""


def _column_from_utf8_byte_offset(line: str, byte_offset: int) -> int:
    """Convert ripgrep's UTF-8 byte offset into a 1-based character column."""

    prefix = line.encode("utf-8", errors="replace")[:byte_offset]
    return len(prefix.decode("utf-8", errors="replace")) + 1


def _build_rg_command(
    pattern: str,
    roots: Sequence[Path],
    *,
    regex: bool,
    include: Sequence[str] | None,
    ignore_case: bool,
    hidden: bool,
) -> list[str]:
    command = [
        "rg",
        "--json",
        "--line-number",
        "--column",
    ]

    if ignore_case:
        command.append("--ignore-case")

    if not regex:
        command.append("--fixed-strings")

    if hidden:
        command.append("--hidden")

    if include:
        for pattern_glob in include:
            command.extend(["--glob", pattern_glob])

    command.extend(["--", pattern])
    command.extend(str(root) for root in roots)
    return command


def search_with_rg(
    pattern: str,
    roots: Sequence[Path],
    *,
    regex: bool = True,
    include: Sequence[str] | None = None,
    ignore_case: bool = False,
    hidden: bool = False,
) -> list[SearchResult]:
    """Search with ripgrep and parse its JSON event stream."""

    command = _build_rg_command(
        pattern,
        roots,
        regex=regex,
        include=include,
        ignore_case=ignore_case,
        hidden=hidden,
    )

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    # ripgrep exit codes: 0 = match, 1 = no match, 2 = error.
    if process.returncode == 1:
        return []
    if process.returncode != 0:
        raise SearchBackendError(process.stderr.strip() or "ripgrep failed")

    results: list[SearchResult] = []

    for raw_event in process.stdout.splitlines():
        if not raw_event:
            continue

        event = json.loads(raw_event)
        if event.get("type") != "match":
            continue

        data = event["data"]
        path = Path(_decode_json_text(data["path"]))
        line_number = int(data["line_number"])
        line = _decode_json_text(data["lines"]).rstrip("\r\n")
        submatches = data.get("submatches") or []

        if not submatches:
            results.append(
                SearchResult(
                    path=path,
                    line_number=line_number,
                    column=None,
                    line=line,
                    match=None,
                    backend="rg",
                )
            )
            continue

        for submatch in submatches:
            match_text = _decode_json_text(submatch.get("match", {}))
            start = int(submatch["start"])
            results.append(
                SearchResult(
                    path=path,
                    line_number=line_number,
                    column=_column_from_utf8_byte_offset(line, start),
                    line=line,
                    match=match_text,
                    backend="rg",
                )
            )

    return results
