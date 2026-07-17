from __future__ import annotations

import json
from pathlib import Path

import pytest


pytest.importorskip("langchain_core")
pytest.importorskip("pydantic")

from pygreptool.langchain_tool import (
    create_langchain_find_files_tool,
    create_langchain_read_context_tool,
    create_langchain_search_tool,
)


def test_langchain_find_files_tool_returns_safe_structured_candidates(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "alpha_service.py").write_text("alpha\n", encoding="utf-8")
    (src / "worker.txt").write_text("worker\n", encoding="utf-8")
    find_tool = create_langchain_find_files_tool(workspace_root=tmp_path, allowed_roots=["src"])

    raw = find_tool.invoke({"folder": "src", "name_query": "service", "extensions": ["py"]})
    result = json.loads(raw)

    assert find_tool.name == "find_files"
    assert "Do not use for text inside a file" in find_tool.description
    assert result["ok"] is True
    assert result["results"] == [
        {"path": str(src / "alpha_service.py"), "name": "alpha_service.py", "extension": "py"}
    ]


def test_langchain_find_files_tool_rejects_escape_from_allowed_roots(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    find_tool = create_langchain_find_files_tool(workspace_root=tmp_path, allowed_roots=["src"])

    result = json.loads(find_tool.invoke({"folder": ".."}))

    assert result["ok"] is False
    assert "outside allowed_roots" in result["error"]["message"]


def test_langchain_search_tool_invokes_pygreptool(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO from langchain tool\n", encoding="utf-8")
    search_tool = create_langchain_search_tool(allowed_roots=[tmp_path])

    raw = search_tool.invoke(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "smart",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["path"].endswith("app.py")
    assert result["results"][0]["backend"] == "python"


def test_langchain_search_tool_only_includes_context_when_requested(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("before\nTODO target\nafter\n", encoding="utf-8")
    search_tool = create_langchain_search_tool(allowed_roots=[tmp_path])

    compact = json.loads(
        search_tool.invoke({"pattern": "TODO", "roots": [str(tmp_path)], "backend": "python"})
    )
    expanded = json.loads(
        search_tool.invoke(
            {
                "pattern": "TODO",
                "roots": [str(tmp_path)],
                "backend": "python",
                "include_context": True,
                "context_before": 1,
                "context_after": 1,
            }
        )
    )

    assert "context" not in compact["results"][0]
    assert expanded["results"][0]["context"]["content"] == "before\nTODO target\nafter"


def test_langchain_search_tool_rejects_roots_outside_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    disallowed = tmp_path / "disallowed"
    allowed.mkdir()
    disallowed.mkdir()
    (disallowed / "secret.py").write_text("TODO secret\n", encoding="utf-8")
    search_tool = create_langchain_search_tool(allowed_roots=[allowed])

    raw = search_tool.invoke(
        {
            "pattern": "TODO",
            "roots": [str(disallowed)],
            "regex": False,
            "backend": "smart",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is False
    assert result["error"]["type"] == "ToolInputError"
    assert "outside allowed_roots" in result["error"]["message"]


def test_langchain_search_tool_schema_guides_focused_search(tmp_path: Path) -> None:
    search_tool = create_langchain_search_tool(allowed_roots=[tmp_path])

    assert search_tool.name == "search_code"
    assert "Do not use for filenames" in search_tool.description
    schema = search_tool.args_schema.model_json_schema()
    assert schema["properties"]["backend"]["default"] == "smart"
    assert "project-relative paths" in schema["properties"]["roots"]["description"]
    assert "[:=]" in schema["properties"]["pattern"]["description"]
    assert "context_before" in schema["properties"]
    assert "context_after" in schema["properties"]
    assert schema["properties"]["include_context"]["default"] is False
    assert "workspace_root" not in schema["properties"]
    assert "ignore_files" not in schema["properties"]
    assert "read_context_args" in search_tool.description


def test_langchain_search_tool_returns_retry_hints_for_empty_results(tmp_path: Path) -> None:
    search_tool = create_langchain_search_tool(allowed_roots=[tmp_path])

    raw = search_tool.invoke(
        {
            "pattern": "MISSING_NEEDLE",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "smart",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["count"] == 0
    assert "hints" in result
    assert "shorter stable token" in result["hints"][0]


def test_langchain_search_tool_resolves_roots_from_workspace_root(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    src_dir = tmp_path / "src"
    other_dir = tmp_path / "other"
    src_dir.mkdir()
    other_dir.mkdir()
    target = src_dir / "app.py"
    target.write_text("TODO from langchain workspace\n", encoding="utf-8")
    monkeypatch.chdir(other_dir)
    search_tool = create_langchain_search_tool(workspace_root=tmp_path, allowed_roots=["src"])

    raw = search_tool.invoke(
        {
            "pattern": "TODO",
            "roots": ["src"],
            "regex": False,
            "backend": "smart",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["path"] == str(target)


def test_langchain_read_context_tool_respects_workspace_and_allowed_roots(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    src_dir = tmp_path / "src"
    other_dir = tmp_path / "other"
    src_dir.mkdir()
    other_dir.mkdir()
    target = src_dir / "app.py"
    target.write_text("one\nTODO from read tool\nthree\n", encoding="utf-8")
    monkeypatch.chdir(other_dir)
    read_tool = create_langchain_read_context_tool(workspace_root=tmp_path, allowed_roots=["src"])

    raw = read_tool.invoke(
        {
            "path": "src/app.py",
            "line_number": 2,
            "before": 1,
            "after": 1,
            "full": False,
            "max_lines": 200,
            "max_chars": 20000,
            "encoding": "utf-8",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["path"] == str(target)
    assert result["content"] == "one\nTODO from read tool\nthree"
    assert result["count"] == 3
    assert result["summary"] == f"Read 3 line(s) from {target} (lines 1-3)."
    assert result["next_step"]


def test_langchain_read_context_tool_rejects_outside_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    disallowed = tmp_path / "disallowed"
    allowed.mkdir()
    disallowed.mkdir()
    target = disallowed / "secret.py"
    target.write_text("secret\n", encoding="utf-8")
    read_tool = create_langchain_read_context_tool(allowed_roots=[allowed])

    raw = read_tool.invoke(
        {
            "path": str(target),
            "line_number": 1,
            "before": 0,
            "after": 0,
            "full": False,
            "max_lines": 200,
            "max_chars": 20000,
            "encoding": "utf-8",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is False
    assert "outside allowed_roots" in result["error"]["message"]
