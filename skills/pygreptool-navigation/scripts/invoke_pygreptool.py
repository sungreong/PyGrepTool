"""Dispatch one config-bound PyGrepTool request for an agent skill.

This script deliberately has no search orchestration. The agent chooses one tool;
the script loads trusted project policy and dispatches that exact tool only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from lightweight_runtime import DENY, LightweightError, run_request as run_lightweight_request


TOOL_NAMES = {"find_files", "search_code", "read_context"}


class ConfigurationError(ValueError):
    """Raised when a project policy configuration is unsafe or malformed."""


def _read_json(source: str) -> Any:
    if source == "-":
        text = sys.stdin.read()
    else:
        candidate = Path(source)
        text = candidate.read_text(encoding="utf-8") if candidate.is_file() else source
    try:
        return json.loads(text.removeprefix("\ufeff"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"expected JSON input: {exc}") from exc


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{field} must be a JSON object")
    return value


def _project_relative_paths(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{field} must be a non-empty array of project-relative paths")

    paths: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ConfigurationError(f"{field}[{index}] must be a non-empty string")
        candidate = Path(item)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ConfigurationError(f"{field}[{index}] must stay inside the configuration directory")
        paths.append(item)
    return paths


def _string_list(value: Any, field: str, *, default: tuple[str, ...]) -> list[str]:
    if value is None:
        return list(default)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigurationError(f"{field} must be an array of non-empty strings")
    return list(value)


def _optional_positive_int(value: Any, field: str, *, maximum: int) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise ConfigurationError(f"{field} must be an integer between 1 and {maximum}")
    return value


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def load_project_config(config_path: Path) -> dict[str, Any]:
    """Load a trusted project-local configuration without allowing scope escape."""

    raw = _require_mapping(_read_json(str(config_path)), "configuration")
    allowed_roots = _project_relative_paths(raw.get("allowed_roots", ["."]), "allowed_roots")
    ignore_files = _project_relative_paths(raw.get("ignore_files", [".gitignore"]), "ignore_files")
    respect_ignore = raw.get("respect_ignore", True)
    if not isinstance(respect_ignore, bool):
        raise ConfigurationError("respect_ignore must be a boolean")

    policy_raw = _require_mapping(raw.get("policy", {}), "policy")
    custom_deny = _string_list(policy_raw.get("deny_globs"), "policy.deny_globs", default=())
    extra_redaction = _string_list(policy_raw.get("redaction_patterns"), "policy.redaction_patterns", default=())
    max_file_size = policy_raw.get("max_file_size_bytes", 2 * 1024 * 1024)
    if not isinstance(max_file_size, int) or isinstance(max_file_size, bool) or max_file_size < 1:
        raise ConfigurationError("policy.max_file_size_bytes must be a positive integer")
    scan_limits = {
        "max_files_scanned": _optional_positive_int(policy_raw.get("max_files_scanned"), "policy.max_files_scanned", maximum=100000),
        "max_total_bytes_scanned": _optional_positive_int(
            policy_raw.get("max_total_bytes_scanned"), "policy.max_total_bytes_scanned", maximum=1024 * 1024 * 1024
        ),
        "timeout_ms": _optional_positive_int(policy_raw.get("timeout_ms"), "policy.timeout_ms", maximum=60000),
    }

    return {
        "workspace_root": config_path.parent.resolve(),
        "allowed_roots": allowed_roots,
        "allowed_paths": [(config_path.parent / path).resolve() for path in allowed_roots],
        "ignore_files": ignore_files,
        "respect_ignore": respect_ignore,
        "deny_globs": _unique([*DENY, *custom_deny]),
        "redaction_patterns": extra_redaction,
        "max_file_size_bytes": max_file_size,
        "scan_limits": scan_limits,
    }


def default_project_config(workspace_root: Path) -> dict[str, Any]:
    """Use the current directory as one virtual, read-only workspace by default."""

    workspace = workspace_root.resolve()
    return {
        "workspace_root": workspace,
        "allowed_roots": ["."],
        "allowed_paths": [workspace],
        "ignore_files": [".gitignore", ".pygrepignore"],
        "respect_ignore": True,
        "deny_globs": list(DENY),
        "redaction_patterns": [],
        "max_file_size_bytes": 2 * 1024 * 1024,
        "scan_limits": {"max_files_scanned": None, "max_total_bytes_scanned": None, "timeout_ms": None},
    }


def initialize_project_files(config_path: Path, *, allowed_roots: list[str] | None, create_ignore: bool) -> dict[str, Any]:
    """Create opt-in project configuration without overwriting user files."""

    if config_path.exists():
        raise ConfigurationError(f"configuration already exists: {config_path}")
    roots = allowed_roots or ["."]
    _project_relative_paths(roots, "allowed_roots")
    config_path.write_text(
        json.dumps(
            {
                "allowed_roots": roots,
                "ignore_files": [".gitignore", ".pygrepignore"],
                "respect_ignore": True,
                "policy": {
                    "deny_globs": [],
                    "max_file_size_bytes": 2 * 1024 * 1024,
                    "max_files_scanned": None,
                    "max_total_bytes_scanned": None,
                    "timeout_ms": None,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created = [str(config_path)]
    ignore_path = config_path.parent / ".pygrepignore"
    if create_ignore and not ignore_path.exists():
        ignore_path.write_text("# Agent-search-only exclusions. Add generated or noisy paths below.\n# build/\n# dist/\n", encoding="utf-8")
        created.append(str(ignore_path))
    return {"ok": True, "tool": "runner_setup", "created": created, "summary": "Created trusted PyGrepTool project configuration.", "error": None}


def run_request(request: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one selected tool under a fixed virtual workspace boundary."""

    tool_name = request.get("tool")
    arguments = request.get("arguments")
    if tool_name not in TOOL_NAMES:
        raise ConfigurationError("tool must be one of: find_files, search_code, read_context")
    if not isinstance(arguments, Mapping):
        raise ConfigurationError("arguments must be a JSON object")
    bounded_arguments = dict(arguments)
    if tool_name == "search_code":
        for field, configured_limit in config.get("scan_limits", {}).items():
            if configured_limit is None:
                continue
            requested_limit = bounded_arguments.get(field)
            if not isinstance(requested_limit, int) or isinstance(requested_limit, bool) or requested_limit > configured_limit:
                bounded_arguments[field] = configured_limit
    bounded_request = {"tool": tool_name, "arguments": bounded_arguments}

    try:
        from pygreptool import CodeAccessPolicy, run_find_files_tool, run_read_context_tool, run_search_tool
        from pygreptool.security_policy import DEFAULT_REDACTION_PATTERNS
    except ModuleNotFoundError as exc:
        if exc.name != "pygreptool":
            raise
        return run_lightweight_request(bounded_request, config)

    common = {
        "workspace_root": config["workspace_root"],
        "allowed_roots": config["allowed_roots"],
        "virtual_mode": True,
        "policy": CodeAccessPolicy(
            deny_globs=config["deny_globs"],
            redaction_patterns=_unique([*DEFAULT_REDACTION_PATTERNS, *config["redaction_patterns"]]),
            max_file_size_bytes=config["max_file_size_bytes"],
        ),
    }
    if tool_name == "find_files":
        result = run_find_files_tool(
            bounded_arguments,
            **common,
            respect_ignore=config["respect_ignore"],
            ignore_files=config["ignore_files"],
        )
        result["runtime"] = "package"
        return result
    if tool_name == "search_code":
        result = run_search_tool(
            bounded_arguments,
            **common,
            respect_ignore=config["respect_ignore"],
            ignore_files=config["ignore_files"],
        )
        result["runtime"] = "package"
        return result
    result = run_read_context_tool(bounded_arguments, **common)
    result["runtime"] = "package"
    return result


def create_policy_bound_dispatcher(config_path: Path) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Bind one reviewed config for a host-owned tool integration.

    Use this factory when an agent receives a direct Python tool rather than a
    shell command. The model supplies only ``tool`` and ``arguments``; it cannot
    choose another config path or modify policy fields through the request.
    This remains a tool-level boundary and must run inside the intended sandbox.
    """

    config = load_project_config(config_path.resolve())

    def dispatch(request: Mapping[str, Any]) -> dict[str, Any]:
        result = run_request(request, config)
        result["config_mode"] = "policy_bound"
        return result

    return dispatch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch one PyGrepTool request with trusted project policy.")
    parser.add_argument("--config", help="Optional trusted project configuration path. Defaults to the current directory only.")
    parser.add_argument("--init-config", action="store_true", help="Create .pygreptool.json without overwriting an existing file.")
    parser.add_argument("--init-ignore", action="store_true", help="With --init-config, also create a commented .pygrepignore template.")
    parser.add_argument("--allowed-root", action="append", help="Repeat while initializing to set trusted project-relative roots.")
    parser.add_argument(
        "--request",
        default="-",
        help="JSON request, JSON file path, or '-' for stdin. Request fields: tool and arguments.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.init_ignore and not args.init_config:
            raise ConfigurationError("--init-ignore requires --init-config")
        if args.init_config:
            config_path = Path(args.config).resolve() if args.config else Path.cwd() / ".pygreptool.json"
            result = initialize_project_files(config_path, allowed_roots=args.allowed_root, create_ignore=args.init_ignore)
            print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
            return 0
        request = _require_mapping(_read_json(args.request), "request")
        config = load_project_config(Path(args.config).resolve()) if args.config else default_project_config(Path.cwd())
        result = run_request(request, config)
        result["config_mode"] = "configured" if args.config else "default_current_directory"
    except Exception as exc:  # Keep the runner protocol JSON-only for agent callers.
        result = {
            "ok": False,
            "tool": "runner",
            "summary": "PyGrepTool request could not run under the configured project policy.",
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
