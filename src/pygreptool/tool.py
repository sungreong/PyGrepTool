from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .core import (
    DEFAULT_IGNORE_FILES,
    BackendName,
    PathInput,
    SearchResult,
    read_context,
    resolve_search_roots,
    search,
)
from .path_policy import AgentPathMapper
from .runtime_scope import (
    ToolInputError,
    resolve_effective_allowed_roots,
    resolve_path_for_tool_workspace,
    resolve_tool_workspace_root,
    validate_tool_allowed_roots,
)
from .security_policy import CodeAccessPolicy

TOOL_NAME = "search_code"
TOOL_NAME_READ_CONTEXT = "read_context"
TOOL_DESCRIPTION = (
    "Search text inside policy-allowed project files. Use for code, symbols, TODOs, imports, and configuration keys. "
    "Do not use for filename discovery; use find_files. Returns exact path, line, column, and read_context_args."
)
TOOL_DESCRIPTION_READ_CONTEXT = (
    "Read a bounded line range from one policy-allowed file. Use after search_code to verify a selected match."
)

_BACKEND_VALUES = ["auto", "smart", "rg", "grep", "python"]
_DEFAULT_MAX_RESULTS = 50
_DEFAULT_MAX_LINE_CHARS = 500
_DEFAULT_CONTEXT_BEFORE = 3
_DEFAULT_CONTEXT_AFTER = 3
_DEFAULT_READ_BEFORE = 20
_DEFAULT_READ_AFTER = 20
_DEFAULT_READ_MAX_LINES = 200
_DEFAULT_READ_MAX_CHARS = 20000

_STRICT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Text or regular expression pattern to search for.",
        },
        "roots": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": (
                "Files or directories to search. Prefer project-relative paths such as "
                "['src', 'tests'] rather than broad paths like ['/']."
            ),
        },
        "regex": {
            "type": ["boolean", "null"],
            "description": "Whether pattern is a regular expression. Use false for literal text search.",
        },
        "include": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "Optional glob filters. Examples: ['*.py'], ['src/**/*.ts', '*.md'].",
        },
        "ignore_case": {
            "type": ["boolean", "null"],
            "description": "Whether to search case-insensitively.",
        },
        "hidden": {
            "type": ["boolean", "null"],
            "description": "Whether to include hidden files and directories when supported.",
        },
        "backend": {
            "type": ["string", "null"],
            "enum": [*_BACKEND_VALUES, None],
            "description": (
                "Search backend. smart uses Python for small roots and external search for larger roots. "
                "auto tries rg, then grep, then pure Python fallback."
            ),
        },
        "fallback": {
            "type": ["boolean", "null"],
            "description": "In auto mode, whether to try the next backend when a backend fails.",
        },
        "encoding": {
            "type": ["string", "null"],
            "description": "Text encoding for Python backend and grep output decoding. Usually utf-8.",
        },
        "max_results": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 1000,
            "description": "Maximum number of matches to return. Null uses the tool default.",
        },
        "max_line_chars": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 20000,
            "description": "Maximum characters kept from each matching line. Long lines are truncated.",
        },
        "context_before": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 20,
            "description": "Number of lines to include before each match. Null uses the tool default.",
        },
        "context_after": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 20,
            "description": "Number of lines to include after each match. Null uses the tool default.",
        },
        "include_context": {
            "type": ["boolean", "null"],
            "description": (
                "Whether results should include nearby lines. Use false for compact discovery and read_context "
                "for selected matches."
            ),
        },
    },
    # Strict function schemas require every property to be listed as required.
    # Optional fields are represented by allowing null and applying defaults in the handler.
    "required": [
        "pattern",
        "roots",
        "regex",
        "include",
        "ignore_case",
        "hidden",
        "backend",
        "fallback",
        "encoding",
        "max_results",
        "max_line_chars",
        "context_before",
        "context_after",
        "include_context",
    ],
    "additionalProperties": False,
}

_READ_CONTEXT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "File path to read. Prefer project-relative paths returned by search_code.",
        },
        "line_number": {
            "type": ["integer", "null"],
            "minimum": 1,
            "description": "1-based line number to read around. Required unless full is true.",
        },
        "before": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 200,
            "description": "Number of lines to read before line_number. Null uses the tool default.",
        },
        "after": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 200,
            "description": "Number of lines to read after line_number. Null uses the tool default.",
        },
        "full": {
            "type": ["boolean", "null"],
            "description": "Whether to read a bounded slice from the start of the whole file.",
        },
        "max_lines": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 2000,
            "description": "Maximum lines to return. Null uses the tool default.",
        },
        "max_chars": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 100000,
            "description": "Maximum total line characters to return. Null uses the tool default.",
        },
        "encoding": {
            "type": ["string", "null"],
            "description": "Text encoding for reading the file. Usually utf-8.",
        },
    },
    "required": [
        "path",
        "line_number",
        "before",
        "after",
        "full",
        "max_lines",
        "max_chars",
        "encoding",
    ],
    "additionalProperties": False,
}


def get_openai_responses_tool_schema(*, strict: bool = True) -> dict[str, Any]:
    """Return an OpenAI Responses API style function-tool schema."""

    schema: dict[str, Any] = {
        "type": "function",
        "name": TOOL_NAME,
        "description": TOOL_DESCRIPTION,
        "parameters": copy.deepcopy(_STRICT_PARAMETERS),
    }
    if strict:
        schema["strict"] = True
    return schema


def get_openai_chat_tool_schema(*, strict: bool = True) -> dict[str, Any]:
    """Return an OpenAI Chat Completions style function-tool schema."""

    function_schema: dict[str, Any] = {
        "name": TOOL_NAME,
        "description": TOOL_DESCRIPTION,
        "parameters": copy.deepcopy(_STRICT_PARAMETERS),
    }
    if strict:
        function_schema["strict"] = True
    return {"type": "function", "function": function_schema}


def get_openai_responses_read_context_tool_schema(*, strict: bool = True) -> dict[str, Any]:
    """Return an OpenAI Responses API style read_context function-tool schema."""

    schema: dict[str, Any] = {
        "type": "function",
        "name": TOOL_NAME_READ_CONTEXT,
        "description": TOOL_DESCRIPTION_READ_CONTEXT,
        "parameters": copy.deepcopy(_READ_CONTEXT_PARAMETERS),
    }
    if strict:
        schema["strict"] = True
    return schema


def get_openai_chat_read_context_tool_schema(*, strict: bool = True) -> dict[str, Any]:
    """Return an OpenAI Chat Completions style read_context function-tool schema."""

    function_schema: dict[str, Any] = {
        "name": TOOL_NAME_READ_CONTEXT,
        "description": TOOL_DESCRIPTION_READ_CONTEXT,
        "parameters": copy.deepcopy(_READ_CONTEXT_PARAMETERS),
    }
    if strict:
        function_schema["strict"] = True
    return {"type": "function", "function": function_schema}


OPENAI_RESPONSES_TOOL_SCHEMA = get_openai_responses_tool_schema()
OPENAI_CHAT_TOOL_SCHEMA = get_openai_chat_tool_schema()
OPENAI_RESPONSES_READ_CONTEXT_TOOL_SCHEMA = get_openai_responses_read_context_tool_schema()
OPENAI_CHAT_READ_CONTEXT_TOOL_SCHEMA = get_openai_chat_read_context_tool_schema()


def _as_mapping(arguments: Mapping[str, Any] | str) -> Mapping[str, Any]:
    if isinstance(arguments, str):
        arguments = arguments.removeprefix("\ufeff")
        try:
            loaded = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ToolInputError(f"arguments must be valid JSON: {exc}") from exc
        if not isinstance(loaded, Mapping):
            raise ToolInputError("arguments JSON must decode to an object")
        return loaded

    if not isinstance(arguments, Mapping):
        raise ToolInputError("arguments must be a mapping or a JSON object string")

    return arguments


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ToolInputError(f"{field} must be a non-empty string")
    return value


def _optional_bool(value: Any, field: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolInputError(f"{field} must be a boolean or null")
    return value


def _optional_int(value: Any, field: str, default: int | None, *, minimum: int, maximum: int) -> int | None:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolInputError(f"{field} must be an integer or null")
    if not minimum <= value <= maximum:
        raise ToolInputError(f"{field} must be between {minimum} and {maximum}")
    return value


def _optional_string(value: Any, field: str, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value == "":
        raise ToolInputError(f"{field} must be a non-empty string or null")
    return value


def _normalize_roots(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ToolInputError("roots must be a non-empty array of path strings")

    roots: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or item == "":
            raise ToolInputError(f"roots[{index}] must be a non-empty string")
        roots.append(item)
    return roots


def _normalize_include(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ToolInputError("include must be an array of glob strings or null")

    include: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or item == "":
            raise ToolInputError(f"include[{index}] must be a non-empty string")
        include.append(item)
    return include or None


def _normalize_backend(value: Any) -> BackendName:
    if value is None:
        return "auto"
    if value not in _BACKEND_VALUES:
        raise ToolInputError("backend must be one of: auto, smart, rg, grep, python, or null")
    return value  # type: ignore[return-value]


def normalize_tool_arguments(arguments: Mapping[str, Any] | str) -> dict[str, Any]:
    """Normalize function-call arguments and apply runtime defaults."""

    raw = dict(_as_mapping(arguments))

    # Convenience for manual calls: allow {"root": "src"} as an alias for
    # the strict schema's {"roots": ["src"]}. The exported schema still uses
    # roots so agents can search multiple paths when needed.
    if "root" in raw:
        if "roots" in raw:
            raise ToolInputError("use either root or roots, not both")
        root_value = raw.pop("root")
        if not isinstance(root_value, str) or root_value == "":
            raise ToolInputError("root must be a non-empty string")
        raw["roots"] = [root_value]

    allowed_fields = set(_STRICT_PARAMETERS["properties"])
    unknown_fields = sorted(set(raw) - allowed_fields)
    if unknown_fields:
        joined = ", ".join(unknown_fields)
        raise ToolInputError(f"unknown argument field(s): {joined}")

    if "pattern" not in raw:
        raise ToolInputError("pattern is required")
    if "roots" not in raw:
        raise ToolInputError("roots is required")

    max_results = _optional_int(
        raw.get("max_results"),
        "max_results",
        _DEFAULT_MAX_RESULTS,
        minimum=0,
        maximum=1000,
    )
    max_line_chars = _optional_int(
        raw.get("max_line_chars"),
        "max_line_chars",
        _DEFAULT_MAX_LINE_CHARS,
        minimum=1,
        maximum=20000,
    )
    context_before = _optional_int(
        raw.get("context_before"),
        "context_before",
        _DEFAULT_CONTEXT_BEFORE,
        minimum=0,
        maximum=20,
    )
    context_after = _optional_int(
        raw.get("context_after"),
        "context_after",
        _DEFAULT_CONTEXT_AFTER,
        minimum=0,
        maximum=20,
    )

    return {
        "pattern": _require_string(raw.get("pattern"), "pattern"),
        "roots": _normalize_roots(raw.get("roots")),
        "regex": _optional_bool(raw.get("regex"), "regex", True),
        "include": _normalize_include(raw.get("include")),
        "ignore_case": _optional_bool(raw.get("ignore_case"), "ignore_case", False),
        "hidden": _optional_bool(raw.get("hidden"), "hidden", False),
        "backend": _normalize_backend(raw.get("backend")),
        "fallback": _optional_bool(raw.get("fallback"), "fallback", True),
        "encoding": _optional_string(raw.get("encoding"), "encoding", "utf-8"),
        "max_results": max_results,
        "max_line_chars": max_line_chars,
        "context_before": context_before,
        "context_after": context_after,
        "include_context": _optional_bool(raw.get("include_context"), "include_context", True),
    }


def normalize_read_context_arguments(arguments: Mapping[str, Any] | str) -> dict[str, Any]:
    """Normalize read_context function-call arguments and apply runtime defaults."""

    raw = dict(_as_mapping(arguments))
    allowed_fields = set(_READ_CONTEXT_PARAMETERS["properties"])
    unknown_fields = sorted(set(raw) - allowed_fields)
    if unknown_fields:
        joined = ", ".join(unknown_fields)
        raise ToolInputError(f"unknown argument field(s): {joined}")

    if "path" not in raw:
        raise ToolInputError("path is required")

    line_number = _optional_int(raw.get("line_number"), "line_number", None, minimum=1, maximum=10_000_000)
    full = _optional_bool(raw.get("full"), "full", False)
    if not full and line_number is None:
        raise ToolInputError("line_number is required when full is false")

    return {
        "path": _require_string(raw.get("path"), "path"),
        "line_number": line_number,
        "before": _optional_int(raw.get("before"), "before", _DEFAULT_READ_BEFORE, minimum=0, maximum=200),
        "after": _optional_int(raw.get("after"), "after", _DEFAULT_READ_AFTER, minimum=0, maximum=200),
        "full": full,
        "max_lines": _optional_int(
            raw.get("max_lines"),
            "max_lines",
            _DEFAULT_READ_MAX_LINES,
            minimum=0,
            maximum=2000,
        ),
        "max_chars": _optional_int(
            raw.get("max_chars"),
            "max_chars",
            _DEFAULT_READ_MAX_CHARS,
            minimum=0,
            maximum=100000,
        ),
        "encoding": _optional_string(raw.get("encoding"), "encoding", "utf-8"),
    }


def _truncate_text(text: str, max_chars: int | None) -> tuple[str, bool]:
    if max_chars is None or len(text) <= max_chars:
        return text, False
    if max_chars == 1:
        return "…", True
    return text[: max_chars - 1] + "…", True


def _context_to_tool_dict(context: Any) -> dict[str, Any]:
    return asdict(context)


def _read_context_args_for_result(result: SearchResult, *, path_formatter: Callable[[Path], str] = str) -> dict[str, Any]:
    return {
        "path": path_formatter(result.path),
        "line_number": result.line_number,
        "before": _DEFAULT_READ_BEFORE,
        "after": _DEFAULT_READ_AFTER,
        "full": False,
    }


def search_result_to_tool_dict(
    result: SearchResult,
    *,
    max_line_chars: int | None,
    path_formatter: Callable[[Path], str] = str,
) -> dict[str, Any]:
    """Convert a SearchResult into a JSON-serializable tool result item."""

    data = asdict(result)
    data["path"] = path_formatter(result.path)
    line, truncated = _truncate_text(result.line, max_line_chars)
    data["line"] = line
    data["line_truncated"] = truncated
    if result.context is not None:
        data["context"] = _context_to_tool_dict(result.context)
    else:
        data.pop("context", None)
    data["read_context_args"] = _read_context_args_for_result(result, path_formatter=path_formatter)
    return data


def _redact_serialized_value(value: Any, policy: CodeAccessPolicy | None) -> tuple[Any, bool]:
    if policy is None:
        return value, False
    if isinstance(value, str):
        return policy.redact(value)
    if isinstance(value, list):
        changed = False
        items = []
        for item in value:
            redacted, item_changed = _redact_serialized_value(item, policy)
            items.append(redacted)
            changed = changed or item_changed
        return items, changed
    if isinstance(value, dict):
        changed = False
        items: dict[str, Any] = {}
        for key, item in value.items():
            if key == "path":
                items[key] = item
                continue
            redacted, item_changed = _redact_serialized_value(item, policy)
            items[key] = redacted
            changed = changed or item_changed
        return items, changed
    return value, False


def run_search_tool(
    arguments: Mapping[str, Any] | str,
    *,
    allowed_roots: Sequence[PathInput] | None = None,
    workspace_root: PathInput | None = None,
    virtual_mode: bool = False,
    policy: CodeAccessPolicy | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> dict[str, Any]:
    """Execute the search_code tool and return a JSON-serializable payload.

    This function is the handler you call after an LLM emits a function call named
    ``search_code``. It never raises for normal tool input or backend errors;
    instead, it returns ``ok: false`` with an error object so callers can pass the
    result back to the model safely.
    """

    try:
        normalized = normalize_tool_arguments(arguments)
        runtime_workspace_root, default_to_workspace = resolve_tool_workspace_root(workspace_root, allowed_roots)
        if virtual_mode and not default_to_workspace:
            raise ToolInputError("virtual_mode requires an explicit workspace_root or PYGREPKIT_WORKSPACE_ROOT")
        mapper = AgentPathMapper(runtime_workspace_root, virtual_mode=virtual_mode)
        resolved_roots = resolve_search_roots(normalized["roots"], runtime_workspace_root)
        if virtual_mode:
            resolved_roots = [mapper.to_physical(root) for root in normalized["roots"]]
        effective_allowed_roots = resolve_effective_allowed_roots(
            allowed_roots,
            workspace_root=runtime_workspace_root,
            default_to_workspace=default_to_workspace,
        )
        validate_tool_allowed_roots(resolved_roots, effective_allowed_roots)
        if policy is not None:
            for root in resolved_roots:
                policy.enforce_path(
                    root,
                    workspace_root=runtime_workspace_root,
                    agent_path=mapper.to_agent_path(root),
                    tool=TOOL_NAME,
                    operation="search",
                )
        result_limit = normalized["max_results"]
        probe_limit = result_limit + 1 if result_limit is not None else None

        context_before = normalized["context_before"] if normalized["include_context"] else 0
        context_after = normalized["context_after"] if normalized["include_context"] else 0
        results = search(
            normalized["pattern"],
            resolved_roots,
            regex=normalized["regex"],
            include=normalized["include"],
            ignore_case=normalized["ignore_case"],
            hidden=normalized["hidden"],
            backend=normalized["backend"],
            fallback=normalized["fallback"],
            encoding=normalized["encoding"],
            max_results=probe_limit,
            workspace_root=runtime_workspace_root,
            respect_ignore=respect_ignore,
            ignore_files=ignore_files,
            context_before=context_before,
            context_after=context_after,
        )
        if policy is not None:
            results = [
                result for result in results if policy.allow_result_path(result.path, workspace_root=runtime_workspace_root)
            ]

        max_line_chars = normalized["max_line_chars"]
        truncated = result_limit is not None and len(results) > result_limit
        visible_results = results[:result_limit] if result_limit is not None else results
        items = [
            search_result_to_tool_dict(item, max_line_chars=max_line_chars, path_formatter=mapper.to_agent_path)
            for item in visible_results
        ]
        items, redacted = _redact_serialized_value(items, policy)

        return {
            "ok": True,
            "tool": TOOL_NAME,
            "query": normalized,
            "summary": f"Found {len(items)} match(es).",
            "count": len(items),
            "truncated": truncated,
            "results": items,
            "redacted": redacted,
            "related_tools": [
                {
                    "tool": TOOL_NAME_READ_CONTEXT,
                    "available": True,
                    "reason": "Use this to inspect more surrounding lines or a larger file slice for selected matches.",
                }
            ],
            "next_step": (
                "Call read_context with a result's read_context_args when more surrounding lines are needed."
                if items
                else "Retry with a shorter pattern, regex, or a different allowed root."
            ),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - tool handlers should serialize failures.
        return {
            "ok": False,
            "tool": TOOL_NAME,
            "query": None,
            "summary": "Code search could not run inside the configured project boundary.",
            "count": 0,
            "truncated": False,
            "results": [],
            "related_tools": [
                {
                    "tool": TOOL_NAME_READ_CONTEXT,
                    "available": True,
                    "reason": "Use this to inspect more surrounding lines or a larger file slice for selected matches.",
                }
            ],
            "next_step": "Check the pattern, roots, and allowed_roots, then retry.",
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        }


def run_read_context_tool(
    arguments: Mapping[str, Any] | str,
    *,
    allowed_roots: Sequence[PathInput] | None = None,
    workspace_root: PathInput | None = None,
    virtual_mode: bool = False,
    policy: CodeAccessPolicy | None = None,
) -> dict[str, Any]:
    """Execute the read_context tool and return a JSON-serializable payload."""

    try:
        normalized = normalize_read_context_arguments(arguments)
        runtime_workspace_root, default_to_workspace = resolve_tool_workspace_root(workspace_root, allowed_roots)
        if virtual_mode and not default_to_workspace:
            raise ToolInputError("virtual_mode requires an explicit workspace_root or PYGREPKIT_WORKSPACE_ROOT")
        mapper = AgentPathMapper(runtime_workspace_root, virtual_mode=virtual_mode)
        effective_allowed_roots = resolve_effective_allowed_roots(
            allowed_roots,
            workspace_root=runtime_workspace_root,
            default_to_workspace=default_to_workspace,
        )
        resolved_input_path = mapper.to_physical(normalized["path"])
        if policy is not None:
            policy.enforce_path(
                resolved_input_path,
                workspace_root=runtime_workspace_root,
                agent_path=mapper.to_agent_path(resolved_input_path),
                tool=TOOL_NAME_READ_CONTEXT,
                operation="read",
            )
        context = read_context(
            resolved_input_path,
            line_number=normalized["line_number"],
            before=normalized["before"],
            after=normalized["after"],
            full=normalized["full"],
            max_lines=normalized["max_lines"],
            max_chars=normalized["max_chars"],
            workspace_root=runtime_workspace_root,
            allowed_roots=effective_allowed_roots,
            encoding=normalized["encoding"],
        )
        resolved_path = resolve_path_for_tool_workspace(resolved_input_path, runtime_workspace_root)

        content, content_redacted = _redact_serialized_value(context.content, policy)
        lines, lines_redacted = _redact_serialized_value([asdict(line) for line in context.lines], policy)
        agent_path = mapper.to_agent_path(resolved_path)
        line_count = len(context.lines)
        return {
            "ok": True,
            "tool": TOOL_NAME_READ_CONTEXT,
            "path": agent_path,
            "start_line": context.start_line,
            "end_line": context.end_line,
            "summary": f"Read {line_count} line(s) from {agent_path} (lines {context.start_line}-{context.end_line}).",
            "count": line_count,
            "content": content,
            "lines": lines,
            "redacted": content_redacted or lines_redacted,
            "truncated": context.truncated,
            "related_tools": [
                {
                    "tool": TOOL_NAME,
                    "available": True,
                    "reason": "Use search_code to find more evidence in the allowed workspace.",
                }
            ],
            "next_step": "Use this bounded file evidence in the final answer or run another focused search.",
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - tool handlers should serialize failures.
        return {
            "ok": False,
            "tool": TOOL_NAME_READ_CONTEXT,
            "path": None,
            "start_line": None,
            "end_line": None,
            "summary": "File context could not be read inside the configured project boundary.",
            "count": 0,
            "content": "",
            "lines": [],
            "truncated": False,
            "related_tools": [],
            "next_step": "Use a policy-allowed path returned by search_code and retry.",
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        }


def allowed_roots_from_env(env_var: str = "PYGREPKIT_ALLOWED_ROOTS") -> list[str] | None:
    """Read allowed roots from an os.pathsep-separated environment variable."""

    raw = os.environ.get(env_var)
    if not raw:
        return None
    return [part for part in raw.split(os.pathsep) if part]


def create_search_tool_runner(
    *,
    workspace_root: PathInput | None = None,
    virtual_mode: bool = False,
    policy: CodeAccessPolicy | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> Callable[[Mapping[str, Any] | str], dict[str, Any]]:
    """Create a configured ``search_code`` runner for model function-call arguments."""

    def runner(arguments: Mapping[str, Any] | str) -> dict[str, Any]:
        return run_search_tool(
            arguments,
            workspace_root=workspace_root,
            virtual_mode=virtual_mode,
            policy=policy,
            allowed_roots=allowed_roots,
            respect_ignore=respect_ignore,
            ignore_files=ignore_files,
        )

    return runner


def create_read_context_tool_runner(
    *,
    workspace_root: PathInput | None = None,
    virtual_mode: bool = False,
    policy: CodeAccessPolicy | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
) -> Callable[[Mapping[str, Any] | str], dict[str, Any]]:
    """Create a configured ``read_context`` runner for model function-call arguments."""

    def runner(arguments: Mapping[str, Any] | str) -> dict[str, Any]:
        return run_read_context_tool(
            arguments,
            workspace_root=workspace_root,
            virtual_mode=virtual_mode,
            policy=policy,
            allowed_roots=allowed_roots,
        )

    return runner


def get_tool_spec(format: str = "responses", tool_name: str = TOOL_NAME) -> dict[str, Any]:
    """Return an OpenAI-compatible function tool schema.

    ``responses`` returns the Responses API shape. ``chat_completions`` returns
    the Chat Completions shape where function fields are nested under ``function``.
    ``tool_name`` accepts ``find_files``, ``search_code``, or ``read_context``.
    """

    if tool_name == "find_files":
        from .file_tool import get_openai_chat_find_files_tool_schema, get_openai_responses_find_files_tool_schema

        if format == "responses":
            return get_openai_responses_find_files_tool_schema()
        if format == "chat_completions":
            return get_openai_chat_find_files_tool_schema()
        raise ValueError("format must be one of: responses, chat_completions")
    if tool_name == TOOL_NAME_READ_CONTEXT:
        if format == "responses":
            return get_openai_responses_read_context_tool_schema()
        if format == "chat_completions":
            return get_openai_chat_read_context_tool_schema()
        raise ValueError("format must be one of: responses, chat_completions")
    if tool_name != TOOL_NAME:
        raise ValueError("tool_name must be one of: find_files, search_code, read_context")
    if format == "responses":
        return get_openai_responses_tool_schema()
    if format == "chat_completions":
        return get_openai_chat_tool_schema()
    raise ValueError("format must be one of: responses, chat_completions")

# Backward-friendly aliases for consumers that expect generic names.
OPENAI_RESPONSES_TOOL = OPENAI_RESPONSES_TOOL_SCHEMA
OPENAI_CHAT_COMPLETIONS_TOOL = OPENAI_CHAT_TOOL_SCHEMA
search_files_tool = run_search_tool
# Deprecated alias. Kept so older agent configs can still call the same handler.
search_code_tool = run_search_tool
read_context_tool = run_read_context_tool


def _run_find_files_tool_proxy(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Load the optional file-discovery handler without creating an import cycle."""

    from .file_tool import run_find_files_tool

    return run_find_files_tool(*args, **kwargs)


TOOL_FUNCTIONS = {
    TOOL_NAME: run_search_tool,
    "search_files": run_search_tool,
    "find_files": _run_find_files_tool_proxy,
    TOOL_NAME_READ_CONTEXT: run_read_context_tool,
}
