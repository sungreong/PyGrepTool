from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field

from pygreptool.core import DEFAULT_IGNORE_FILES, PathInput
from pygreptool.tool import run_read_context_tool, run_search_tool


class SearchCodeInput(BaseModel):
    """Input schema for the LangChain search_code tool."""

    pattern: str = Field(
        description=(
            "Text or regular expression to search for. For code variants, prefer regex such as "
            "[\"']?backend[\"']?\\s*[:=]\\s*[\"']smart[\"'] instead of one exact quote/spacing style."
        )
    )
    roots: list[str] = Field(
        default_factory=lambda: ["."],
        description=(
            "Files or directories to search. Prefer project-relative paths like ['src', 'tests']. "
            "When the tool has a configured workspace or allowed scope, relative roots are resolved inside it."
        ),
    )
    regex: bool = Field(default=False, description="Whether pattern is a regular expression.")
    include: list[str] | None = Field(
        default=None,
        description="Optional glob filters such as ['*.py'] or ['src/**/*.md'].",
    )
    ignore_case: bool = Field(default=False, description="Whether to search case-insensitively.")
    hidden: bool = Field(default=False, description="Whether to include hidden files and directories.")
    backend: str = Field(
        default="smart",
        description="Search backend: smart, auto, rg, grep, or python. Use smart by default.",
    )
    max_results: int = Field(default=20, ge=0, le=1000, description="Maximum number of matches to return.")
    max_line_chars: int = Field(default=300, ge=1, le=20000, description="Maximum characters kept per line.")
    context_before: int = Field(default=3, ge=0, le=20, description="Lines of context before each match.")
    context_after: int = Field(default=3, ge=0, le=20, description="Lines of context after each match.")


class ReadContextInput(BaseModel):
    """Input schema for the LangChain read_context tool."""

    path: str = Field(description="File path to read. Prefer the path from a search_code result.")
    line_number: int | None = Field(
        default=None,
        ge=1,
        description="1-based line number to read around. Required unless full is true.",
    )
    before: int = Field(default=20, ge=0, le=200, description="Lines to read before line_number.")
    after: int = Field(default=20, ge=0, le=200, description="Lines to read after line_number.")
    full: bool = Field(default=False, description="Read a bounded slice from the start of the whole file.")
    max_lines: int = Field(default=200, ge=0, le=2000, description="Maximum lines to return.")
    max_chars: int = Field(default=20000, ge=0, le=100000, description="Maximum total line characters.")
    encoding: str = Field(default="utf-8", description="Text encoding for reading the file.")


def _default_allowed_roots() -> list[str]:
    raw = os.environ.get("PYGREPKIT_ALLOWED_ROOTS")
    if raw:
        return [part for part in raw.split(os.pathsep) if part]
    return [str(Path.cwd())]


def _search_code_handler(
    pattern: str,
    roots: list[str] | None = None,
    regex: bool = False,
    include: list[str] | None = None,
    ignore_case: bool = False,
    hidden: bool = False,
    backend: str = "smart",
    max_results: int = 20,
    max_line_chars: int = 300,
    context_before: int = 3,
    context_after: int = 3,
    *,
    workspace_root: PathInput | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> str:
    payload = {
        "pattern": pattern,
        "roots": roots or ["."],
        "regex": regex,
        "include": include,
        "ignore_case": ignore_case,
        "hidden": hidden,
        "backend": backend,
        "max_results": max_results,
        "max_line_chars": max_line_chars,
        "context_before": context_before,
        "context_after": context_after,
    }
    default_allowed_roots = allowed_roots
    if default_allowed_roots is None and workspace_root is None:
        default_allowed_roots = _default_allowed_roots()
    result = run_search_tool(
        payload,
        workspace_root=workspace_root,
        allowed_roots=default_allowed_roots,
        respect_ignore=respect_ignore,
        ignore_files=ignore_files,
    )
    if result.get("ok") is True and result.get("count") == 0:
        result["hints"] = [
            "If the exact phrase failed, retry with a shorter stable token.",
            "For code key/value variants, use regex with optional key quotes, whitespace, and ':' or '=' such as [\"']?key[\"']?\\s*[:=]\\s*[\"']value[\"'].",
            "Try focused roots inside the allowed project root, for example ['src'], ['tests'], or ['docs'].",
        ]
    return json.dumps(result, ensure_ascii=False)


def create_langchain_search_tool(
    *,
    workspace_root: PathInput | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
):
    """Create a LangChain StructuredTool wrapper around pygreptool's search_code handler."""

    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise ImportError(
            "LangChain integration requires langchain-core. "
            "Install the optional agent dependencies before using create_langchain_search_tool()."
        ) from exc

    roots_scope = list(allowed_roots) if allowed_roots is not None else None
    ignore_file_scope = tuple(ignore_files)

    def search_code(
        pattern: str,
        roots: list[str] | None = None,
        regex: bool = False,
        include: list[str] | None = None,
        ignore_case: bool = False,
        hidden: bool = False,
        backend: str = "smart",
        max_results: int = 20,
        max_line_chars: int = 300,
        context_before: int = 3,
        context_after: int = 3,
    ) -> str:
        """Search local project files and return JSON matches with path, line, column, text, and backend."""

        return _search_code_handler(
            pattern,
            roots=roots,
            regex=regex,
            include=include,
            ignore_case=ignore_case,
            hidden=hidden,
            backend=backend,
            max_results=max_results,
            max_line_chars=max_line_chars,
            context_before=context_before,
            context_after=context_after,
            workspace_root=workspace_root,
            allowed_roots=roots_scope,
            respect_ignore=respect_ignore,
            ignore_files=ignore_file_scope,
        )

    return StructuredTool.from_function(
        search_code,
        name="search_code",
        description=(
            "Search local project files for exact text or regex and return JSON matches. "
            "Use this before answering questions about where code, tests, docs, TODOs, imports, "
            "or symbols appear in the repository. Prefer backend='smart' and focused roots. "
            "Relative roots like ['src'] are interpreted inside the configured workspace or allowed scope. "
            "If you need more context for a result, call read_context with that result's read_context_args. "
            "If an exact string search returns no results, retry with a shorter token or a regex "
            "that handles quote/spacing/key-value variants, such as [\"']?key[\"']?\\s*[:=]\\s*[\"']value[\"'], "
            "before concluding nothing exists."
        ),
        args_schema=SearchCodeInput,
    )


def create_langchain_read_context_tool(
    *,
    workspace_root: PathInput | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
):
    """Create a LangChain StructuredTool wrapper around pygreptool's read_context handler."""

    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise ImportError(
            "LangChain integration requires langchain-core. "
            "Install the optional agent dependencies before using create_langchain_read_context_tool()."
        ) from exc

    roots_scope = list(allowed_roots) if allowed_roots is not None else None

    def read_context(
        path: str,
        line_number: int | None = None,
        before: int = 20,
        after: int = 20,
        full: bool = False,
        max_lines: int = 200,
        max_chars: int = 20000,
        encoding: str = "utf-8",
    ) -> str:
        """Read a bounded file slice around a line or from the start of a file."""

        result = run_read_context_tool(
            {
                "path": path,
                "line_number": line_number,
                "before": before,
                "after": after,
                "full": full,
                "max_lines": max_lines,
                "max_chars": max_chars,
                "encoding": encoding,
            },
            workspace_root=workspace_root,
            allowed_roots=roots_scope,
        )
        return json.dumps(result, ensure_ascii=False)

    return StructuredTool.from_function(
        read_context,
        name="read_context",
        description=(
            "Read surrounding lines or a bounded full-file slice from one local project file. "
            "Use this with search_code result read_context_args when a match needs more context."
        ),
        args_schema=ReadContextInput,
    )
