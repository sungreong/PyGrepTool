from __future__ import annotations

import json
from pathlib import Path

import pytest

from pygreptool import (
    TOOL_NAME,
    create_search_tool_runner,
    run_read_context_tool,
    get_openai_chat_tool_schema,
    get_openai_responses_tool_schema,
    run_search_tool,
)
from pygreptool import tool_cli


def test_responses_tool_schema_is_strict_function_schema() -> None:
    schema = get_openai_responses_tool_schema()

    assert schema["type"] == "function"
    assert schema["name"] == TOOL_NAME
    assert schema["strict"] is True
    assert schema["parameters"]["additionalProperties"] is False
    assert set(schema["parameters"]["required"]) == set(schema["parameters"]["properties"])
    assert "smart" in schema["parameters"]["properties"]["backend"]["enum"]


def test_chat_tool_schema_is_nested_function_schema() -> None:
    schema = get_openai_chat_tool_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == TOOL_NAME
    assert schema["function"]["strict"] is True
    assert schema["function"]["parameters"]["additionalProperties"] is False


def test_run_search_tool_returns_json_serializable_results(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("alpha\nTODO from tool\nomega\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "include": ["*.py"],
            "ignore_case": None,
            "hidden": None,
            "backend": "python",
            "fallback": None,
            "encoding": None,
            "max_results": 10,
            "max_line_chars": 200,
        }
    )

    assert result["ok"] is True
    assert result["tool"] == TOOL_NAME
    assert result["count"] == 1
    assert result["results"][0]["path"].endswith("app.py")
    assert result["results"][0]["line_number"] == 2
    assert result["results"][0]["column"] == 1
    assert result["results"][0]["match"] == "TODO"
    assert result["results"][0]["context"]["start_line"] == 1
    assert result["results"][0]["context"]["content"] == "alpha\nTODO from tool\nomega"
    assert result["results"][0]["read_context_args"]["line_number"] == 2
    assert result["related_tools"][0]["tool"] == "read_context"
    json.dumps(result, ensure_ascii=False)


def test_run_search_tool_accepts_smart_backend(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO from smart tool\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(target)],
            "regex": False,
            "backend": "smart",
        }
    )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["backend"] == "python"


def test_run_search_tool_can_disable_context(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\nTODO no context\nthree\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "python",
            "context_before": 0,
            "context_after": 0,
        }
    )

    assert result["ok"] is True
    assert "context" not in result["results"][0]


def test_run_search_tool_context_null_uses_default(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\nTODO default\nfour\nfive\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "python",
            "context_before": None,
            "context_after": None,
        }
    )

    assert result["ok"] is True
    assert result["results"][0]["context"]["start_line"] == 1
    assert result["results"][0]["context"]["end_line"] == 5


def test_run_search_tool_accepts_json_string_and_truncates_lines(tmp_path: Path) -> None:
    target = tmp_path / "long.txt"
    target.write_text("TODO " + "x" * 50 + "\n", encoding="utf-8")

    result = run_search_tool(
        json.dumps(
            {
                "pattern": "TODO",
                "roots": [str(tmp_path)],
                "regex": False,
                "backend": "python",
                "max_line_chars": 12,
            }
        )
    )

    assert result["ok"] is True
    assert result["results"][0]["line"] == "TODO xxxxxx…"
    assert result["results"][0]["line_truncated"] is True


def test_run_search_tool_accepts_json_string_with_utf8_bom(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO from powershell pipe\n", encoding="utf-8")

    result = run_search_tool(
        "\ufeff"
        + json.dumps(
            {
                "pattern": "TODO",
                "roots": [str(tmp_path)],
                "regex": False,
                "backend": "python",
            }
        )
    )

    assert result["ok"] is True
    assert result["count"] == 1


def test_run_search_tool_marks_result_limit_truncated_only_when_more_results_exist(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO only\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "python",
            "max_results": 1,
        }
    )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["truncated"] is False


def test_run_search_tool_marks_result_limit_truncated_when_more_results_exist(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO one\nTODO two\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "python",
            "max_results": 1,
        }
    )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["truncated"] is True
    assert result["results"][0]["line"] == "TODO one"


def test_run_search_tool_can_report_truncated_with_zero_max_results(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO hidden by limit\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "python",
            "max_results": 0,
        }
    )

    assert result["ok"] is True
    assert result["count"] == 0
    assert result["truncated"] is True
    assert result["results"] == []


def test_run_search_tool_rejects_roots_outside_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    disallowed = tmp_path / "disallowed"
    allowed.mkdir()
    disallowed.mkdir()
    (disallowed / "secret.txt").write_text("TODO\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(disallowed)],
            "regex": False,
            "backend": "python",
        },
        allowed_roots=[allowed],
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "ToolInputError"
    assert "outside allowed_roots" in result["error"]["message"]


def test_run_search_tool_resolves_roots_from_workspace_root(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    src_dir = tmp_path / "src"
    other_dir = tmp_path / "other"
    src_dir.mkdir()
    other_dir.mkdir()
    target = src_dir / "app.py"
    target.write_text("TODO from workspace\n", encoding="utf-8")
    monkeypatch.chdir(other_dir)

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": ["src"],
            "regex": False,
            "backend": "python",
        },
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["path"] == str(target)


def test_run_search_tool_resolves_allowed_roots_from_workspace_root(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    target = src_dir / "app.py"
    target.write_text("TODO allowed\n", encoding="utf-8")

    allowed = run_search_tool(
        {
            "pattern": "TODO",
            "roots": ["src"],
            "regex": False,
            "backend": "python",
        },
        workspace_root=tmp_path,
        allowed_roots=["src"],
    )
    rejected = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [".."],
            "regex": False,
            "backend": "python",
        },
        workspace_root=tmp_path,
        allowed_roots=["src"],
    )

    assert allowed["ok"] is True
    assert allowed["count"] == 1
    assert rejected["ok"] is False
    assert rejected["error"]["type"] == "ToolInputError"


def test_run_search_tool_uses_workspace_root_env_var(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    src_dir = tmp_path / "src"
    other_dir = tmp_path / "other"
    src_dir.mkdir()
    other_dir.mkdir()
    target = src_dir / "app.py"
    target.write_text("TODO from env\n", encoding="utf-8")
    monkeypatch.chdir(other_dir)
    monkeypatch.setenv("PYGREPKIT_WORKSPACE_ROOT", str(tmp_path))

    result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": ["src"],
            "regex": False,
            "backend": "python",
        }
    )

    assert result["ok"] is True
    assert result["results"][0]["path"] == str(target)


def test_create_search_tool_runner_keeps_runtime_configuration(tmp_path: Path) -> None:
    pytest.importorskip("pathspec")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    kept = src_dir / "kept.py"
    ignored = src_dir / "ignored.py"
    kept.write_text("TODO kept\n", encoding="utf-8")
    ignored.write_text("TODO ignored\n", encoding="utf-8")
    (tmp_path / ".agentignore").write_text("src/ignored.py\n", encoding="utf-8")
    runner = create_search_tool_runner(
        workspace_root=tmp_path,
        allowed_roots=["src"],
        ignore_files=(".agentignore",),
    )

    result = runner(
        {
            "pattern": "TODO",
            "roots": ["src"],
            "regex": False,
            "backend": "python",
        }
    )

    assert result["ok"] is True
    assert [item["path"] for item in result["results"]] == [str(kept)]


def test_search_result_read_context_args_can_call_read_context_tool(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("\n".join(f"line {index}" for index in range(1, 31)) + "\nTODO target\n", encoding="utf-8")
    search_result = run_search_tool(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "python",
            "context_before": 0,
            "context_after": 0,
        }
    )

    context_result = run_read_context_tool(search_result["results"][0]["read_context_args"])

    assert context_result["ok"] is True
    assert context_result["tool"] == "read_context"
    assert context_result["start_line"] == 11
    assert context_result["end_line"] == 31
    assert context_result["content"].endswith("TODO target")


def test_run_read_context_tool_resolves_workspace_relative_path(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    src_dir = tmp_path / "src"
    other_dir = tmp_path / "other"
    src_dir.mkdir()
    other_dir.mkdir()
    target = src_dir / "app.py"
    target.write_text("one\nTODO context\nthree\n", encoding="utf-8")
    monkeypatch.chdir(other_dir)

    result = run_read_context_tool(
        {
            "path": "src/app.py",
            "line_number": 2,
            "before": 1,
            "after": 1,
            "full": False,
            "max_lines": 200,
            "max_chars": 20000,
            "encoding": "utf-8",
        },
        workspace_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["path"] == str(target)
    assert result["content"] == "one\nTODO context\nthree"


def test_run_read_context_tool_rejects_path_outside_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    disallowed = tmp_path / "disallowed"
    allowed.mkdir()
    disallowed.mkdir()
    target = disallowed / "secret.py"
    target.write_text("secret\n", encoding="utf-8")

    result = run_read_context_tool(
        {
            "path": str(target),
            "line_number": 1,
            "before": 0,
            "after": 0,
            "full": False,
            "max_lines": 200,
            "max_chars": 20000,
            "encoding": "utf-8",
        },
        allowed_roots=[allowed],
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "ValueError"
    assert "outside allowed_roots" in result["error"]["message"]


def test_run_read_context_tool_full_mode_respects_limits(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = run_read_context_tool(
        {
            "path": str(target),
            "line_number": None,
            "before": None,
            "after": None,
            "full": True,
            "max_lines": 2,
            "max_chars": 20000,
            "encoding": None,
        }
    )

    assert result["ok"] is True
    assert result["content"] == "one\ntwo"
    assert result["truncated"] is True


def test_tool_cli_prints_schema(capsys) -> None:  # type: ignore[no-untyped-def]
    exit_code = tool_cli.main(["--schema", "responses"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["name"] == TOOL_NAME


def test_tool_cli_executes_call_from_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "app.py"
    target.write_text("TODO from cli tool\n", encoding="utf-8")
    args = json.dumps(
        {
            "pattern": "TODO",
            "roots": [str(tmp_path)],
            "regex": False,
            "backend": "python",
        }
    )

    exit_code = tool_cli.main(["--call", args])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["results"][0]["path"].endswith("app.py")
