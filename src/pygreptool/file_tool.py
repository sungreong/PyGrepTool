"""OpenAI-compatible handler for high-level file discovery."""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Callable, Mapping, Sequence

from .core import DEFAULT_IGNORE_FILES, PathInput
from .file_discovery import find_files, normalize_extensions
from .path_policy import AgentPathMapper
from .runtime_scope import ToolInputError, resolve_effective_allowed_roots, resolve_tool_workspace_root
from .security_policy import CodeAccessPolicy

TOOL_NAME_FIND_FILES = "find_files"
TOOL_DESCRIPTION_FIND_FILES = (
    "Find filenames in the allowed workspace. Use for folder, filename, or extension requests. "
    "Do not use for text inside a file; use search_code instead. Returns only policy-allowed files."
)
_DEFAULT_MAX_RESULTS = 20

_FIND_FILES_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "folder": {
            "type": "string",
            "description": "Project-relative folder to inspect, for example 'src' or 'docs'.",
        },
        "name_query": {
            "type": ["string", "null"],
            "description": "Optional case-insensitive filename text, for example 'service'. Do not use this for file contents.",
        },
        "extensions": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "Optional extensions such as ['py'] or ['.py', 'md']. Both forms are accepted.",
        },
        "max_results": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 1000,
            "description": "Maximum files to return. Null uses the tool default.",
        },
        "hidden": {
            "type": ["boolean", "null"],
            "description": "Whether to include hidden files and directories. Null uses false.",
        },
    },
    "required": ["folder", "name_query", "extensions", "max_results", "hidden"],
    "additionalProperties": False,
}


def get_openai_responses_find_files_tool_schema(*, strict: bool = True) -> dict[str, Any]:
    """Return a Responses API schema for ``find_files``."""

    schema: dict[str, Any] = {
        "type": "function",
        "name": TOOL_NAME_FIND_FILES,
        "description": TOOL_DESCRIPTION_FIND_FILES,
        "parameters": copy.deepcopy(_FIND_FILES_PARAMETERS),
    }
    if strict:
        schema["strict"] = True
    return schema


def get_openai_chat_find_files_tool_schema(*, strict: bool = True) -> dict[str, Any]:
    """Return a Chat Completions API schema for ``find_files``."""

    function_schema: dict[str, Any] = {
        "name": TOOL_NAME_FIND_FILES,
        "description": TOOL_DESCRIPTION_FIND_FILES,
        "parameters": copy.deepcopy(_FIND_FILES_PARAMETERS),
    }
    if strict:
        function_schema["strict"] = True
    return {"type": "function", "function": function_schema}


def _as_mapping(arguments: Mapping[str, Any] | str) -> Mapping[str, Any]:
    if isinstance(arguments, str):
        import json

        try:
            value = json.loads(arguments.removeprefix("\ufeff"))
        except json.JSONDecodeError as exc:
            raise ToolInputError(f"arguments must be valid JSON: {exc}") from exc
        if not isinstance(value, Mapping):
            raise ToolInputError("arguments JSON must decode to an object")
        return value
    if not isinstance(arguments, Mapping):
        raise ToolInputError("arguments must be a mapping or a JSON object string")
    return arguments


def normalize_find_files_arguments(arguments: Mapping[str, Any] | str) -> dict[str, Any]:
    """Validate high-level file discovery arguments and apply safe defaults."""

    raw = dict(_as_mapping(arguments))
    unknown = sorted(set(raw) - set(_FIND_FILES_PARAMETERS["properties"]))
    if unknown:
        raise ToolInputError(f"unknown argument field(s): {', '.join(unknown)}")

    folder = raw.get("folder", ".")
    if not isinstance(folder, str) or not folder:
        raise ToolInputError("folder must be a non-empty string")
    name_query = raw.get("name_query")
    if name_query is not None and (not isinstance(name_query, str) or not name_query.strip()):
        raise ToolInputError("name_query must be a non-empty string or null")
    extensions = raw.get("extensions")
    if extensions is not None and not isinstance(extensions, list):
        raise ToolInputError("extensions must be an array of strings or null")
    try:
        normalized_extensions = normalize_extensions(extensions)
    except ValueError as exc:
        raise ToolInputError(str(exc)) from exc
    max_results = raw.get("max_results")
    if max_results is None:
        max_results = _DEFAULT_MAX_RESULTS
    if not isinstance(max_results, int) or isinstance(max_results, bool) or not 0 <= max_results <= 1000:
        raise ToolInputError("max_results must be an integer between 0 and 1000 or null")
    hidden = raw.get("hidden")
    if hidden is None:
        hidden = False
    if not isinstance(hidden, bool):
        raise ToolInputError("hidden must be a boolean or null")
    return {
        "folder": folder,
        "name_query": name_query,
        "extensions": list(normalized_extensions) if normalized_extensions else None,
        "max_results": max_results,
        "hidden": hidden,
    }


def _result_summary(query: Mapping[str, Any], count: int, *, truncated: bool) -> str:
    extension_text = "all extensions"
    if query["extensions"]:
        extension_text = ", ".join(f".{extension}" for extension in query["extensions"])
    name_text = f" whose names contain '{query['name_query']}'" if query["name_query"] else ""
    suffix = " Results were limited." if truncated else ""
    return f"Found {count} file(s) in '{query['folder']}' with {extension_text}{name_text}.{suffix}"


def run_find_files_tool(
    arguments: Mapping[str, Any] | str,
    *,
    allowed_roots: Sequence[PathInput] | None = None,
    workspace_root: PathInput | None = None,
    virtual_mode: bool = False,
    policy: CodeAccessPolicy | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> dict[str, Any]:
    """Execute ``find_files`` and serialize safe, bounded candidate file metadata."""

    try:
        normalized = normalize_find_files_arguments(arguments)
        runtime_workspace, default_to_workspace = resolve_tool_workspace_root(workspace_root, allowed_roots)
        if virtual_mode and not default_to_workspace:
            raise ToolInputError("virtual_mode requires an explicit workspace_root or PYGREPKIT_WORKSPACE_ROOT")
        mapper = AgentPathMapper(runtime_workspace, virtual_mode=virtual_mode)
        resolved_folder = mapper.to_physical(normalized["folder"])
        if policy is not None:
            policy.enforce_path(
                resolved_folder,
                workspace_root=runtime_workspace,
                agent_path=mapper.to_agent_path(resolved_folder),
                tool=TOOL_NAME_FIND_FILES,
                operation="discover",
            )
        effective_allowed = resolve_effective_allowed_roots(
            allowed_roots,
            workspace_root=runtime_workspace,
            default_to_workspace=default_to_workspace,
        )
        probe_limit = normalized["max_results"] + 1
        matches = find_files(
            resolved_folder,
            name_query=normalized["name_query"],
            extensions=normalized["extensions"],
            hidden=normalized["hidden"],
            workspace_root=runtime_workspace,
            allowed_roots=effective_allowed,
            respect_ignore=respect_ignore,
            ignore_files=ignore_files,
        )[:probe_limit]
        if policy is not None:
            matches = [match for match in matches if policy.allow_result_path(match.path, workspace_root=runtime_workspace)]
        truncated = len(matches) > normalized["max_results"]
        visible = matches[: normalized["max_results"]]
        return {
            "ok": True,
            "tool": TOOL_NAME_FIND_FILES,
            "query": normalized,
            "summary": _result_summary(normalized, len(visible), truncated=truncated),
            "count": len(visible),
            "truncated": truncated,
            "results": [asdict(match) | {"path": mapper.to_agent_path(match.path)} for match in visible],
            "related_tools": [
                {
                    "tool": "search_code",
                    "available": True,
                    "reason": "Use a result path as a focused search_code root to inspect text inside that file.",
                }
            ],
            "next_step": "Use a returned path as a focused search_code root when you need to inspect file contents.",
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - tool handlers serialize expected agent errors.
        return {
            "ok": False,
            "tool": TOOL_NAME_FIND_FILES,
            "query": None,
            "summary": "File discovery could not run inside the configured project boundary.",
            "count": 0,
            "truncated": False,
            "results": [],
            "related_tools": [],
            "next_step": "Check folder and allowed_roots, then retry with a project-relative folder.",
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def create_find_files_tool_runner(
    *,
    workspace_root: PathInput | None = None,
    virtual_mode: bool = False,
    policy: CodeAccessPolicy | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
) -> Callable[[Mapping[str, Any] | str], dict[str, Any]]:
    """Create a configured ``find_files`` function-call handler."""

    def runner(arguments: Mapping[str, Any] | str) -> dict[str, Any]:
        return run_find_files_tool(
            arguments,
            workspace_root=workspace_root,
            virtual_mode=virtual_mode,
            policy=policy,
            allowed_roots=allowed_roots,
            respect_ignore=respect_ignore,
            ignore_files=ignore_files,
        )

    return runner
