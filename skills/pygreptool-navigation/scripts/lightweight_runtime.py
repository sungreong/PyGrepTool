"""Zero-dependency fallback with the same public request contract as PyGrepTool."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Mapping
import os
import re
import time


DENY = (".env", ".env.*", ".git", ".git/**", "*.pem", "*.key", "id_rsa*", "**/*.pem", "**/*.key", "**/id_rsa*")
SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}
REDACT = (r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{20,}\b", r"\bAKIA[0-9A-Z]{16}\b", r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[^\s,;]+")
SEARCH_FIELDS = {
    "pattern", "roots", "regex", "include", "ignore_case", "hidden", "backend", "fallback", "encoding", "max_results",
    "max_line_chars", "context_before", "context_after", "include_context", "max_files_scanned", "max_total_bytes_scanned", "timeout_ms",
}
READ_FIELDS = {"path", "line_number", "before", "after", "full", "max_lines", "max_chars", "encoding"}
FIND_FIELDS = {"folder", "name_query", "extensions", "max_results", "hidden"}


class LightweightError(ValueError):
    """Base error whose name remains stable in standalone JSON output."""


class ToolInputError(LightweightError):
    """Invalid request or requested path outside the trusted workspace."""


class PolicyDeniedError(LightweightError):
    """Request reached a path denied by the trusted policy."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _agent_path(path: Path, workspace: Path) -> str:
    return "/" + path.resolve(strict=False).relative_to(workspace).as_posix()


def _physical(agent_path: str, workspace: Path) -> Path:
    if not isinstance(agent_path, str) or not agent_path or agent_path.startswith("~"):
        raise ToolInputError("path must be a non-empty virtual path")
    value = agent_path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:", value) or value.startswith("//") or ".." in Path(value).parts:
        raise ToolInputError("path escapes the virtual workspace")
    return (workspace / value.lstrip("/")).resolve(strict=False)


def _denied(path: Path, workspace: Path, globs: list[str]) -> bool:
    try:
        relative = path.resolve(strict=False).relative_to(workspace).as_posix()
    except ValueError:
        return True
    return any(fnmatch(relative, pattern) or fnmatch(path.name, pattern) for pattern in globs)


def _ignored(path: Path, workspace: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(workspace).as_posix()
    return any(fnmatch(relative, pattern.rstrip("/") + ("*" if pattern.endswith("/") else "")) or fnmatch(path.name, pattern) for pattern in patterns)


def _ignore_patterns(workspace: Path, files: list[str]) -> list[str]:
    patterns: list[str] = []
    for name in files:
        candidate = workspace / name
        if candidate.is_file():
            patterns.extend(line.strip().lstrip("/") for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip() and not line.lstrip().startswith(("#", "!")))
    return patterns


def _optional_int(value: Any, field: str, default: int | None, minimum: int, maximum: int) -> int | None:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ToolInputError(f"{field} must be between {minimum} and {maximum}")
    return value


def _optional_bool(value: Any, field: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolInputError(f"{field} must be a boolean or null")
    return value


def _check_fields(args: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ToolInputError(f"unknown argument field(s): {', '.join(unknown)}")


def _files(root: Path, config: Mapping[str, Any], *, hidden: bool, stats: dict[str, Any] | None = None):
    workspace, allowed, globs = config["workspace_root"], config["allowed_paths"], config["deny_globs"]
    if not root.exists() or not any(_inside(root, item) for item in allowed):
        raise ToolInputError("path is outside allowed_roots")
    patterns = _ignore_patterns(workspace, config["ignore_files"]) if config["respect_ignore"] else []
    started = time.monotonic()
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS and (hidden or not name.startswith(".")))
        for name in sorted(names):
            if not hidden and name.startswith("."):
                continue
            path = (Path(current) / name).resolve(strict=False)
            if not _inside(path, workspace) or not any(_inside(path, item) for item in allowed):
                continue
            if _denied(path, workspace, globs) or _ignored(path, workspace, patterns):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > config["max_file_size_bytes"]:
                continue
            if stats is not None:
                if stats["timeout_ms"] is not None and (time.monotonic() - started) * 1000 >= stats["timeout_ms"]:
                    stats["timed_out"] = True
                    return
                if stats["max_files_scanned"] is not None and stats["files_scanned"] >= stats["max_files_scanned"]:
                    stats["budget_exhausted"] = True
                    return
                if stats["max_total_bytes_scanned"] is not None and stats["total_bytes_scanned"] + size > stats["max_total_bytes_scanned"]:
                    stats["files_skipped_by_budget"] += 1
                    stats["budget_exhausted"] = True
                    continue
                stats["files_scanned"] += 1
                stats["total_bytes_scanned"] += size
            yield path


def _redact(text: str) -> tuple[str, bool]:
    redacted = text
    for pattern in REDACT:
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    return redacted, redacted != text


def _search_stats(args: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "files_scanned": 0,
        "total_bytes_scanned": 0,
        "files_skipped_by_budget": 0,
        "files_skipped_binary": 0,
        "budget_exhausted": False,
        "timed_out": False,
        "max_files_scanned": _optional_int(args.get("max_files_scanned"), "max_files_scanned", None, 1, 100000),
        "max_total_bytes_scanned": _optional_int(args.get("max_total_bytes_scanned"), "max_total_bytes_scanned", None, 1, 1024 * 1024 * 1024),
        "timeout_ms": _optional_int(args.get("timeout_ms"), "timeout_ms", None, 1, 60000),
    }


def _context(path: Path, workspace: Path, *, line_number: int | None, before: int, after: int, full: bool, max_lines: int, max_chars: int) -> dict[str, Any]:
    if not full and line_number is None:
        raise ToolInputError("line_number is required when full is false")
    if max_lines == 0 or max_chars == 0:
        return {"start_line": 1, "end_line": 0, "content": "", "lines": [], "truncated": True}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start_index = 0 if full else max(0, line_number - before - 1)
    end_index = len(lines) if full else min(len(lines), line_number + after)
    selected: list[dict[str, Any]] = []
    used_chars, truncated = 0, False
    for index in range(start_index, end_index):
        if len(selected) >= max_lines or used_chars >= max_chars:
            truncated = True
            break
        line = lines[index]
        remaining = max_chars - used_chars
        if len(line) > remaining:
            line = line[:remaining]
            truncated = True
        selected.append({"line_number": index + 1, "line": line, "is_match": line_number == index + 1})
        used_chars += len(line)
        if truncated:
            break
    content, redacted = _redact("\n".join(item["line"] for item in selected))
    if redacted:
        clean_lines = content.split("\n") if content else []
        for item, clean in zip(selected, clean_lines):
            item["line"] = clean
    return {
        "start_line": selected[0]["line_number"] if selected else (1 if full else line_number - before),
        "end_line": selected[-1]["line_number"] if selected else 0,
        "content": content,
        "lines": selected,
        "truncated": truncated,
        "redacted": redacted,
    }


def _run_find(args: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    _check_fields(args, FIND_FIELDS)
    workspace = config["workspace_root"]
    folder = _physical(str(args.get("folder", "/")), workspace)
    extensions = args.get("extensions")
    if extensions is not None and (not isinstance(extensions, list) or not all(isinstance(item, str) and item.strip() for item in extensions)):
        raise ToolInputError("extensions must be an array of strings or null")
    normalized_extensions = [item.lower().lstrip(".") for item in extensions] if extensions else None
    name_query = args.get("name_query")
    if name_query is not None and (not isinstance(name_query, str) or not name_query.strip()):
        raise ToolInputError("name_query must be a non-empty string or null")
    maximum = _optional_int(args.get("max_results"), "max_results", 20, 0, 1000)
    hidden = _optional_bool(args.get("hidden"), "hidden", False)
    matches = []
    for path in _files(folder, config, hidden=hidden):
        if normalized_extensions and path.suffix.lower().lstrip(".") not in normalized_extensions:
            continue
        if name_query and name_query.casefold() not in path.name.casefold():
            continue
        matches.append({"path": _agent_path(path, workspace), "name": path.name, "extension": path.suffix.lstrip(".").lower()})
        if len(matches) > maximum:
            break
    truncated = len(matches) > maximum
    visible = matches[:maximum]
    query = {"folder": str(args.get("folder", "/")), "name_query": name_query, "extensions": normalized_extensions, "max_results": maximum, "hidden": hidden}
    return {
        "ok": True, "tool": "find_files", "query": query, "summary": f"Found {len(visible)} file(s).", "count": len(visible), "truncated": truncated,
        "results": visible, "related_tools": [{"tool": "search_code", "available": True, "reason": "Use a result path as a focused search root to inspect text inside that file."}],
        "next_step": "Use a returned path as a focused search_code root when you need to inspect file contents.", "error": None, "runtime": "standalone",
    }


def _run_search(args: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    _check_fields(args, SEARCH_FIELDS)
    workspace = config["workspace_root"]
    if not isinstance(args.get("pattern"), str) or not args["pattern"]:
        raise ToolInputError("pattern must be a non-empty string")
    roots = args.get("roots")
    if not isinstance(roots, list) or not roots or not all(isinstance(root, str) and root for root in roots):
        raise ToolInputError("roots must be a non-empty array of path strings")
    regex = _optional_bool(args.get("regex"), "regex", True)
    ignore_case = _optional_bool(args.get("ignore_case"), "ignore_case", False)
    hidden = _optional_bool(args.get("hidden"), "hidden", False)
    include = args.get("include")
    if include is not None and (not isinstance(include, list) or not all(isinstance(item, str) and item for item in include)):
        raise ToolInputError("include must be an array of glob strings or null")
    maximum = _optional_int(args.get("max_results"), "max_results", 50, 0, 1000)
    max_line_chars = _optional_int(args.get("max_line_chars"), "max_line_chars", 500, 1, 20000)
    include_context = _optional_bool(args.get("include_context"), "include_context", True)
    before = _optional_int(args.get("context_before"), "context_before", 3, 0, 20)
    after = _optional_int(args.get("context_after"), "context_after", 3, 0, 20)
    flags = re.IGNORECASE if ignore_case else 0
    compiled = re.compile(args["pattern"] if regex else re.escape(args["pattern"]), flags)
    stats = _search_stats(args)
    started = time.monotonic()
    items: list[dict[str, Any]] = []
    for root_name in roots:
        for path in _files(_physical(root_name, workspace), config, hidden=hidden, stats=stats):
            if include and not any(fnmatch(path.name, value) or fnmatch(_agent_path(path, workspace).lstrip("/"), value) for value in include):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                for match in compiled.finditer(line):
                    clean_line, changed_line = _redact(line)
                    clean_match, changed_match = _redact(match.group(0))
                    item = {
                        "path": _agent_path(path, workspace), "line_number": number, "column": match.start() + 1, "line": clean_line,
                        "match": clean_match, "backend": "python", "line_truncated": len(clean_line) > max_line_chars,
                        "read_context_args": {"path": _agent_path(path, workspace), "line_number": number, "before": 20, "after": 20, "full": False},
                    }
                    if item["line_truncated"]:
                        item["line"] = clean_line[: max_line_chars - 1] + "…" if max_line_chars > 1 else "…"
                    if include_context:
                        item["context"] = _context(path, workspace, line_number=number, before=before, after=after, full=False, max_lines=before + after + 1, max_chars=20000)
                    item["redacted"] = changed_line or changed_match or bool(item.get("context", {}).get("redacted"))
                    if "context" in item:
                        item["context"].pop("redacted", None)
                    items.append(item)
                    if len(items) > maximum:
                        break
                if len(items) > maximum:
                    break
            if len(items) > maximum:
                break
        if len(items) > maximum or stats["budget_exhausted"] or stats["timed_out"]:
            break
    truncated = len(items) > maximum or stats["budget_exhausted"] or stats["timed_out"]
    visible = items[:maximum]
    query = {
        "pattern": args["pattern"], "roots": roots, "regex": regex, "include": include, "ignore_case": ignore_case, "hidden": hidden,
        "backend": args.get("backend") or "auto", "fallback": _optional_bool(args.get("fallback"), "fallback", True), "encoding": args.get("encoding") or "utf-8",
        "max_results": maximum, "max_line_chars": max_line_chars, "context_before": before, "context_after": after, "include_context": include_context,
        "max_files_scanned": stats["max_files_scanned"], "max_total_bytes_scanned": stats["max_total_bytes_scanned"], "timeout_ms": stats["timeout_ms"],
    }
    budget_enforced = any(query[key] is not None for key in ("max_files_scanned", "max_total_bytes_scanned", "timeout_ms"))
    stats.update({"duration_ms": round((time.monotonic() - started) * 1000, 2), "budget_enforced": budget_enforced})
    for key in ("max_files_scanned", "max_total_bytes_scanned", "timeout_ms"):
        stats.pop(key)
    if not budget_enforced:
        stats.update({"files_scanned": None, "total_bytes_scanned": None, "files_skipped_by_budget": None, "files_skipped_binary": None})
    return {
        "ok": True, "tool": "search_code", "query": query, "summary": f"Found {len(visible)} match(es).", "count": len(visible), "truncated": truncated,
        "results": visible, "redacted": any(item["redacted"] for item in visible), "search_stats": stats,
        "related_tools": [{"tool": "read_context", "available": True, "reason": "Use this to inspect more surrounding lines or a larger file slice for selected matches."}],
        "next_step": "Call read_context with a result's read_context_args when more surrounding lines are needed." if visible else "Retry with a shorter pattern, regex, or a different allowed root.",
        "error": None, "runtime": "standalone",
    }


def _run_read(args: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    _check_fields(args, READ_FIELDS)
    workspace = config["workspace_root"]
    path = _physical(str(args.get("path", "")), workspace)
    if not path.is_file() or not any(_inside(path, item) for item in config["allowed_paths"]):
        raise ToolInputError("path is outside allowed_roots")
    if _denied(path, workspace, config["deny_globs"]) or path.stat().st_size > config["max_file_size_bytes"]:
        raise PolicyDeniedError("access denied by policy")
    full = _optional_bool(args.get("full"), "full", False)
    line = _optional_int(args.get("line_number"), "line_number", None, 1, 10_000_000)
    if not full and line is None:
        raise ToolInputError("line_number is required when full is false")
    before = _optional_int(args.get("before"), "before", 20, 0, 200)
    after = _optional_int(args.get("after"), "after", 20, 0, 200)
    max_lines = _optional_int(args.get("max_lines"), "max_lines", 200, 0, 2000)
    max_chars = _optional_int(args.get("max_chars"), "max_chars", 20000, 0, 100000)
    context = _context(path, workspace, line_number=line, before=before, after=after, full=full, max_lines=max_lines, max_chars=max_chars)
    agent_path = _agent_path(path, workspace)
    return {
        "ok": True, "tool": "read_context", "path": agent_path, "start_line": context["start_line"], "end_line": context["end_line"],
        "summary": f"Read {len(context['lines'])} line(s) from {agent_path} (lines {context['start_line']}-{context['end_line']}).", "count": len(context["lines"]),
        "content": context["content"], "lines": context["lines"], "redacted": context["redacted"], "truncated": context["truncated"],
        "related_tools": [{"tool": "search_code", "available": True, "reason": "Use search_code to find more evidence in the allowed workspace."}],
        "next_step": "Use this bounded file evidence in the final answer or run another focused search.", "error": None, "runtime": "standalone",
    }


def _error(tool: str, exc: Exception) -> dict[str, Any]:
    if tool == "search_code":
        return {"ok": False, "tool": tool, "query": None, "summary": "Code search could not run inside the configured project boundary.", "count": 0, "truncated": False, "results": [], "search_stats": None, "related_tools": [{"tool": "read_context", "available": True, "reason": "Use this to inspect more surrounding lines or a larger file slice for selected matches."}], "next_step": "Check the pattern, roots, and allowed_roots, then retry.", "error": {"type": exc.__class__.__name__, "message": str(exc)}, "runtime": "standalone"}
    if tool == "find_files":
        return {"ok": False, "tool": tool, "query": None, "summary": "File discovery could not run inside the configured project boundary.", "count": 0, "truncated": False, "results": [], "related_tools": [], "next_step": "Check folder and allowed_roots, then retry with a project-relative folder.", "error": {"type": exc.__class__.__name__, "message": str(exc)}, "runtime": "standalone"}
    return {"ok": False, "tool": tool, "path": None, "start_line": None, "end_line": None, "summary": "File context could not be read inside the configured project boundary.", "count": 0, "content": "", "lines": [], "truncated": False, "related_tools": [], "next_step": "Use a policy-allowed path returned by search_code and retry.", "error": {"type": exc.__class__.__name__, "message": str(exc)}, "runtime": "standalone"}


def run_request(request: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    tool, args = request.get("tool"), request.get("arguments")
    if tool not in {"find_files", "search_code", "read_context"} or not isinstance(args, Mapping):
        raise LightweightError("request needs a supported tool and object arguments")
    try:
        if tool == "find_files":
            return _run_find(args, config)
        if tool == "search_code":
            return _run_search(args, config)
        return _run_read(args, config)
    except Exception as exc:
        return _error(tool, exc)
