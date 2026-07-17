from __future__ import annotations

from pathlib import Path

from pygreptool import CodeAccessPolicy, run_find_files_tool, run_read_context_tool, run_search_tool
from pygreptool.file_discovery import find_files


def _make_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    src = workspace / "src"
    docs = workspace / "docs"
    src.mkdir(parents=True)
    docs.mkdir()
    (src / "alpha_service.py").write_text("alpha\n", encoding="utf-8")
    (src / "beta_service.PY").write_text("beta\n", encoding="utf-8")
    (src / "worker.txt").write_text("worker\n", encoding="utf-8")
    (docs / "operations.md").write_text("docs\n", encoding="utf-8")
    return workspace, src


def test_find_files_filters_scoped_folder_name_and_extensions(tmp_path: Path) -> None:
    workspace, _src = _make_workspace(tmp_path)

    matches = find_files(
        "src",
        name_query="SERVICE",
        extensions=["py"],
        workspace_root=workspace,
        allowed_roots=["src"],
    )

    assert [match.name for match in matches] == ["alpha_service.py", "beta_service.PY"]
    assert [match.extension for match in matches] == ["py", "py"]
    assert all(match.path.is_absolute() for match in matches)


def test_find_files_tool_normalizes_extensions_and_reports_truncation(tmp_path: Path) -> None:
    workspace, _src = _make_workspace(tmp_path)

    result = run_find_files_tool(
        {
            "folder": "src",
            "name_query": "service",
            "extensions": [".py"],
            "max_results": 1,
            "hidden": False,
        },
        workspace_root=workspace,
        allowed_roots=["src"],
    )

    assert result["ok"] is True
    assert result["query"]["extensions"] == ["py"]
    assert result["count"] == 1
    assert result["truncated"] is True
    assert result["summary"] == "Found 1 file(s) in 'src' with .py whose names contain 'service'. Results were limited."
    assert "search_code" in result["next_step"]
    assert result["results"][0]["path"].endswith("alpha_service.py")
    assert result["related_tools"][0]["tool"] == "search_code"


def test_find_files_tool_rejects_folder_outside_allowed_root(tmp_path: Path) -> None:
    workspace, _src = _make_workspace(tmp_path)

    result = run_find_files_tool(
        {"folder": "..", "name_query": None, "extensions": None, "max_results": 20, "hidden": False},
        workspace_root=workspace,
        allowed_roots=["src"],
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "ValueError"
    assert "outside allowed_roots" in result["error"]["message"]


def test_find_files_never_returns_symlink_outside_allowed_roots(tmp_path: Path) -> None:
    workspace, src = _make_workspace(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    link = src / "outside_link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        # Windows development environments may not grant symlink permissions.
        return

    matches = find_files("src", workspace_root=workspace, allowed_roots=["src"], extensions=["py"])

    assert outside.resolve() not in {match.path for match in matches}


def test_virtual_mode_hides_host_paths_and_blocks_escapes(tmp_path: Path) -> None:
    workspace, _src = _make_workspace(tmp_path)

    result = run_find_files_tool(
        {"folder": "/src", "name_query": "service", "extensions": ["py"], "max_results": 20, "hidden": False},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
    )
    escaped = run_find_files_tool(
        {"folder": "/../", "name_query": None, "extensions": None, "max_results": 20, "hidden": False},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
    )
    drive_path = run_find_files_tool(
        {"folder": "C:/Users", "name_query": None, "extensions": None, "max_results": 20, "hidden": False},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
    )

    assert result["ok"] is True
    assert [item["path"] for item in result["results"]] == ["/src/alpha_service.py", "/src/beta_service.PY"]
    assert str(workspace) not in str(result)
    assert escaped["ok"] is False
    assert "cannot contain '..'" in escaped["error"]["message"]
    assert drive_path["ok"] is False
    assert "POSIX-style" in drive_path["error"]["message"]


def test_virtual_mode_round_trips_search_result_into_read_context(tmp_path: Path) -> None:
    workspace, _src = _make_workspace(tmp_path)
    (workspace / "src" / "alpha_service.py").write_text("one\nVIRTUAL_NEEDLE\nthree\n", encoding="utf-8")

    search_result = run_search_tool(
        {"pattern": "VIRTUAL_NEEDLE", "roots": ["/src"], "regex": False, "backend": "python"},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
    )
    context_result = run_read_context_tool(
        search_result["results"][0]["read_context_args"],
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
    )

    assert search_result["results"][0]["path"] == "/src/alpha_service.py"
    assert context_result["ok"] is True
    assert context_result["path"] == "/src/alpha_service.py"
    assert "VIRTUAL_NEEDLE" in context_result["content"]


def test_policy_denies_sensitive_files_redacts_output_and_audits_access(tmp_path: Path) -> None:
    workspace, src = _make_workspace(tmp_path)
    (src / ".env").write_text("API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    (src / "settings.py").write_text("API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    events = []
    policy = CodeAccessPolicy(audit_sink=events.append)

    discovery = run_find_files_tool(
        {"folder": "/src", "name_query": None, "extensions": None, "max_results": 20, "hidden": True},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
        policy=policy,
    )
    search_result = run_search_tool(
        {"pattern": "API_KEY", "roots": ["/src"], "regex": False, "backend": "python"},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
        policy=policy,
    )
    denied_read = run_read_context_tool(
        {"path": "/src/.env", "line_number": 1, "before": 0, "after": 0, "full": False},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
        policy=policy,
    )

    assert "/src/.env" not in {item["path"] for item in discovery["results"]}
    assert search_result["count"] == 1
    assert "[REDACTED]" in search_result["results"][0]["line"]
    assert search_result["redacted"] is True
    assert denied_read["ok"] is False
    assert denied_read["error"]["type"] == "PolicyDeniedError"
    assert [(event.operation, event.decision) for event in events] == [
        ("discover", "allowed"),
        ("search", "allowed"),
        ("read", "denied"),
    ]
