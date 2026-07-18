from __future__ import annotations

from pathlib import Path

from pygreptool import run_find_files_tool, run_read_context_tool, run_search_tool


def test_virtual_mode_never_serializes_host_paths_in_errors(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "private").mkdir()
    (workspace / "private" / "secret.py").write_text("SECRET = True\n", encoding="utf-8")

    responses = [
        run_find_files_tool(
            {"folder": "/private", "name_query": None, "extensions": None, "max_results": 10, "hidden": False},
            workspace_root=workspace,
            allowed_roots=["src"],
            virtual_mode=True,
        ),
        run_search_tool(
            {"pattern": "SECRET", "roots": ["/private"], "regex": False},
            workspace_root=workspace,
            allowed_roots=["src"],
            virtual_mode=True,
        ),
        run_read_context_tool(
            {"path": "/private/secret.py", "line_number": 1, "before": 0, "after": 0, "full": False},
            workspace_root=workspace,
            allowed_roots=["src"],
            virtual_mode=True,
        ),
    ]

    for response in responses:
        assert response["ok"] is False
        assert str(workspace) not in str(response)
        assert "configured virtual workspace" in response["error"]["message"]


def test_budgeted_search_reports_stats_and_stops_after_file_budget(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"{index}.py").write_text(f"NEEDLE_{index} = True\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "NEEDLE",
            "roots": [str(tmp_path)],
            "regex": False,
            "max_results": 10,
            "max_files_scanned": 1,
        },
        workspace_root=tmp_path,
        allowed_roots=["."],
    )

    assert result["ok"] is True
    assert result["search_stats"]["budget_enforced"] is True
    assert result["search_stats"]["files_scanned"] == 1
    assert result["search_stats"]["budget_exhausted"] is True
    assert result["truncated"] is True


def test_budgeted_search_preserves_requested_context_contract(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\nNEEDLE\nthree\n", encoding="utf-8")

    result = run_search_tool(
        {
            "pattern": "NEEDLE",
            "roots": [str(tmp_path)],
            "regex": False,
            "include_context": True,
            "context_before": 1,
            "context_after": 1,
            "max_files_scanned": 5,
        },
        workspace_root=tmp_path,
        allowed_roots=["."],
    )

    assert result["ok"] is True
    assert result["results"][0]["context"]["content"] == "one\nNEEDLE\nthree"
