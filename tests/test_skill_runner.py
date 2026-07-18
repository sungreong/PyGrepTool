from __future__ import annotations

import importlib.util
import subprocess
import sys
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "skills" / "pygreptool-navigation" / "scripts" / "invoke_pygreptool.py"


@pytest.fixture()
def runner_module():
    spec = importlib.util.spec_from_file_location("pygreptool_skill_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_config(workspace: Path, payload: dict[str, object]) -> Path:
    config_path = workspace / ".pygreptool.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


def test_skill_runner_dispatches_one_tool_inside_virtual_allowed_roots(tmp_path: Path, runner_module) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "service.py").write_text("SERVICE_NEEDLE = True\n", encoding="utf-8")
    (src / ".env").write_text("API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        {
            "allowed_roots": ["src"],
            "ignore_files": [".gitignore"],
            "policy": {"deny_globs": ["private/**"]},
        },
    )

    runtime = runner_module.load_project_config(config)
    result = runner_module.run_request(
        {
            "tool": "search_code",
            "arguments": {
                "pattern": "SERVICE_NEEDLE",
                "roots": ["/src"],
                "regex": False,
                "include": ["*.py"],
                "max_results": 10,
                "include_context": False,
            },
        },
        runtime,
    )

    assert result["ok"] is True
    assert result["tool"] == "search_code"
    assert result["results"][0]["path"] == "/src/service.py"
    assert str(tmp_path) not in json.dumps(result)

    denied = runner_module.run_request(
        {
            "tool": "read_context",
            "arguments": {"path": "/src/.env", "line_number": 1, "before": 0, "after": 0, "full": False},
        },
        runtime,
    )
    assert denied["ok"] is False
    assert denied["error"]["type"] == "PolicyDeniedError"


def test_skill_runner_rejects_configured_scope_escape(tmp_path: Path, runner_module) -> None:
    config = write_config(tmp_path, {"allowed_roots": ["../outside"]})

    with pytest.raises(runner_module.ConfigurationError, match="configuration directory"):
        runner_module.load_project_config(config)


def test_skill_runner_cli_emits_json_for_one_selected_tool(tmp_path: Path, runner_module, capsys) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "health.py").write_text("HEALTHCHECK = True\n", encoding="utf-8")
    config = write_config(tmp_path, {"allowed_roots": ["src"]})
    request = json.dumps(
        {
            "tool": "find_files",
            "arguments": {
                "folder": "/src",
                "name_query": "health",
                "extensions": ["py"],
                "max_results": 10,
                "hidden": False,
            },
        }
    )

    exit_code = runner_module.main(["--config", str(config), "--request", request])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["tool"] == "find_files"
    assert payload["results"][0]["path"] == "/src/health.py"


def test_skill_runner_defaults_to_current_directory_workspace(tmp_path: Path, runner_module, monkeypatch, capsys) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "default.py").write_text("DEFAULT_NEEDLE = True\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    request = json.dumps({"tool": "search_code", "arguments": {"pattern": "DEFAULT_NEEDLE", "roots": ["/src"], "regex": False}})

    exit_code = runner_module.main(["--request", request])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["results"][0]["path"] == "/src/default.py"
    assert payload["config_mode"] == "default_current_directory"


def test_skill_runner_initializes_opt_in_config_and_ignore(tmp_path: Path, runner_module, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = runner_module.main(["--init-config", "--init-ignore", "--allowed-root", "src", "--pretty"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["tool"] == "runner_setup"
    config = json.loads((tmp_path / ".pygreptool.json").read_text(encoding="utf-8"))
    assert config["allowed_roots"] == ["src"]
    assert (tmp_path / ".pygrepignore").is_file()


def test_skill_runner_works_without_the_package(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "fallback.py").write_text("FALLBACK_NEEDLE = True\n", encoding="utf-8")
    config = write_config(tmp_path, {"allowed_roots": ["src"], "ignore_files": [".pygrepignore"]})
    (tmp_path / ".pygrepignore").write_text("ignored/\n", encoding="utf-8")
    request = json.dumps({"tool": "search_code", "arguments": {"pattern": "FALLBACK_NEEDLE", "roots": ["/src"], "regex": False}})

    completed = subprocess.run(
        [sys.executable, "-S", str(RUNNER_PATH), "--config", str(config), "--request", request],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["runtime"] == "standalone"
    assert payload["results"][0]["path"] == "/src/fallback.py"


def test_standalone_runner_enforces_max_file_size(tmp_path: Path, runner_module) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "large.py").write_text("LARGE_NEEDLE = '" + "x" * 100 + "'\n", encoding="utf-8")
    config = write_config(tmp_path, {"allowed_roots": ["src"], "policy": {"max_file_size_bytes": 20}})

    result = runner_module.run_lightweight_request(
        {"tool": "search_code", "arguments": {"pattern": "LARGE_NEEDLE", "roots": ["/src"], "regex": False}},
        runner_module.load_project_config(config),
    )

    assert result["ok"] is True
    assert result["count"] == 0


def test_policy_bound_dispatcher_keeps_reviewed_scope_after_config_changes(tmp_path: Path, runner_module) -> None:
    src = tmp_path / "src"
    private = tmp_path / "private"
    src.mkdir()
    private.mkdir()
    (src / "visible.py").write_text("VISIBLE = True\n", encoding="utf-8")
    (private / "secret.py").write_text("SECRET = True\n", encoding="utf-8")
    config = write_config(tmp_path, {"allowed_roots": ["src"]})
    dispatch = runner_module.create_policy_bound_dispatcher(config)

    config.write_text(json.dumps({"allowed_roots": ["private"]}), encoding="utf-8")
    result = dispatch({"tool": "search_code", "arguments": {"pattern": "SECRET", "roots": ["/private"], "regex": False}})

    assert result["ok"] is False
    assert result["config_mode"] == "policy_bound"
    assert str(tmp_path) not in json.dumps(result)


def test_runner_clamps_agent_scan_budget_to_trusted_policy(tmp_path: Path, runner_module) -> None:
    src = tmp_path / "src"
    src.mkdir()
    for index in range(3):
        (src / f"{index}.py").write_text("NEEDLE = True\n", encoding="utf-8")
    config = write_config(tmp_path, {"allowed_roots": ["src"], "policy": {"max_files_scanned": 1}})

    result = runner_module.run_request(
        {
            "tool": "search_code",
            "arguments": {"pattern": "NEEDLE", "roots": ["/src"], "regex": False, "max_files_scanned": 100},
        },
        runner_module.load_project_config(config),
    )

    assert result["ok"] is True
    assert result["query"]["max_files_scanned"] == 1
    assert result["search_stats"]["budget_exhausted"] is True


def test_standalone_runner_matches_package_contract_for_boundary_cases(tmp_path: Path, runner_module) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "visible.py").write_text("one\nNEEDLE\nthree\n", encoding="utf-8")
    (src / ".hidden.py").write_text("NEEDLE hidden\n", encoding="utf-8")
    config = write_config(tmp_path, {"allowed_roots": ["src"]})
    runtime = runner_module.load_project_config(config)
    requests = [
        {"tool": "search_code", "arguments": {"pattern": "NEEDLE", "roots": ["/src"], "regex": False, "max_results": 0}},
        {"tool": "read_context", "arguments": {"path": "/src/visible.py", "line_number": 2, "before": 0, "after": 0, "full": False}},
        {"tool": "read_context", "arguments": {"path": "/src/visible.py", "line_number": None, "full": True, "max_lines": 2, "max_chars": 20000}},
        {"tool": "find_files", "arguments": {"folder": "/src", "name_query": "hidden", "extensions": ["py"], "max_results": 10, "hidden": False}},
    ]

    for request in requests:
        package = runner_module.run_request(request, runtime)
        completed = subprocess.run(
            [sys.executable, "-S", str(RUNNER_PATH), "--config", str(config), "--request", json.dumps(request)],
            check=False,
            capture_output=True,
            text=True,
        )
        standalone = json.loads(completed.stdout)

        assert standalone["ok"] == package["ok"]
        assert standalone["tool"] == package["tool"]
        assert standalone["count"] == package["count"]
        assert standalone["truncated"] == package["truncated"]
        assert standalone.get("path") == package.get("path")
        assert standalone.get("content") == package.get("content")
        assert standalone.get("results") == package.get("results")
