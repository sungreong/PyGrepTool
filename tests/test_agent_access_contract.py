"""Contract tests for safe, evidence-oriented agent code navigation."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from pygreptool import CodeAccessPolicy, run_read_context_tool, run_search_tool


PRIVATE_FIXTURE_MARKER = "HARMLESS_PRIVATE_FIXTURE_MARKER"
REDACTION_FIXTURE_VALUE = "fixture-redaction-value-not-a-real-secret"


@pytest.fixture
def agent_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "agent-workspace"
    src = workspace / "src"
    private = workspace / "private"
    src.mkdir(parents=True)
    private.mkdir()

    (src / "backend.py").write_text(
        "# Fixture configuration\nBACKEND_MODE = 'safe-demo'\n# End fixture\n",
        encoding="utf-8",
    )
    (src / "redaction.py").write_text(
        f"API_TOKEN = '{REDACTION_FIXTURE_VALUE}'\n",
        encoding="utf-8",
    )
    (src / ".env").write_text("FIXTURE_ENV_MARKER=true\n", encoding="utf-8")
    (src / "credentials.yml").write_text("fixture_credential_marker: harmless\n", encoding="utf-8")
    (private / "marker.txt").write_text(f"{PRIVATE_FIXTURE_MARKER}\n", encoding="utf-8")
    return workspace


def _search(arguments: dict[str, object], workspace: Path) -> dict[str, object]:
    return run_search_tool(
        arguments,
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
        policy=CodeAccessPolicy(),
    )


def _read(arguments: dict[str, object], workspace: Path) -> dict[str, object]:
    return run_read_context_tool(
        arguments,
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
        policy=CodeAccessPolicy(),
    )


def test_agent_search_returns_virtual_evidence_with_minimal_context(agent_workspace: Path) -> None:
    result = _search(
        {
            "pattern": "BACKEND_MODE",
            "roots": ["/src"],
            "regex": False,
            "include_context": True,
            "context_before": 1,
            "context_after": 1,
        },
        agent_workspace,
    )

    assert result["ok"] is True
    assert result["count"] == 1
    evidence = result["results"][0]
    assert evidence["path"] == "/src/backend.py"
    assert evidence["line_number"] == 2
    assert evidence["context"]["content"] == "# Fixture configuration\nBACKEND_MODE = 'safe-demo'\n# End fixture"
    assert str(agent_workspace) not in str(result)


def test_private_search_is_denied_without_leaking_marker_or_host_path(agent_workspace: Path) -> None:
    result = _search(
        {"pattern": PRIVATE_FIXTURE_MARKER, "roots": ["/private"], "regex": False},
        agent_workspace,
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "ToolInputError"
    assert PRIVATE_FIXTURE_MARKER not in str(result)
    assert str(agent_workspace) not in str(result)


@pytest.mark.parametrize("path", ["/src/.env", "/src/credentials.yml"])
def test_policy_denies_sensitive_files_even_inside_an_allowed_root(agent_workspace: Path, path: str) -> None:
    search_result = _search({"pattern": "fixture", "roots": [path], "regex": False}, agent_workspace)
    read_result = _read(
        {"path": path, "line_number": 1, "before": 0, "after": 0, "full": False},
        agent_workspace,
    )

    for result in (search_result, read_result):
        assert result["ok"] is False
        assert result["error"]["type"] == "PolicyDeniedError"
        assert "fixture" not in str(result).lower()
        assert str(agent_workspace) not in str(result)


def test_secret_like_values_are_redacted_before_search_results_leave_the_tool(agent_workspace: Path) -> None:
    result = _search({"pattern": "API_TOKEN", "roots": ["/src"], "regex": False}, agent_workspace)

    assert result["ok"] is True
    assert result["redacted"] is True
    assert "[REDACTED]" in str(result["results"])
    assert REDACTION_FIXTURE_VALUE not in str(result)


def test_symlink_escaping_allowed_root_is_denied_for_search_and_read(agent_workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "outside.py").write_text("OUTSIDE_FIXTURE_MARKER = True\n", encoding="utf-8")
    link = agent_workspace / "src" / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available in this environment")

    search_result = _search({"pattern": "OUTSIDE_FIXTURE_MARKER", "roots": ["/src/linked"], "regex": False}, agent_workspace)
    read_result = _read(
        {"path": "/src/linked/outside.py", "line_number": 1, "before": 0, "after": 0, "full": False},
        agent_workspace,
    )

    for result in (search_result, read_result):
        assert result["ok"] is False
        assert "OUTSIDE_FIXTURE_MARKER" not in str(result)
        assert str(outside) not in str(result)


@pytest.mark.parametrize(
    "budget",
    [
        {"max_files_scanned": 1},
        {"max_total_bytes_scanned": 1},
    ],
)
def test_search_reports_truncation_when_a_scan_budget_is_exhausted(tmp_path: Path, budget: dict[str, int]) -> None:
    workspace = tmp_path / "budget-workspace"
    src = workspace / "src"
    src.mkdir(parents=True)
    for index in range(3):
        (src / f"candidate_{index}.py").write_text(f"BUDGET_FIXTURE_MARKER_{index} = True\n", encoding="utf-8")

    result = run_search_tool(
        {"pattern": "BUDGET_FIXTURE_MARKER", "roots": ["/src"], "regex": False, **budget},
        workspace_root=workspace,
        allowed_roots=["src"],
        virtual_mode=True,
        policy=CodeAccessPolicy(),
    )

    assert result["ok"] is True
    assert result["truncated"] is True
    assert result["search_stats"]["budget_enforced"] is True
    assert result["search_stats"]["budget_exhausted"] is True


@pytest.mark.parametrize(
    "denied_call",
    [
        lambda workspace: _search({"pattern": "anything", "roots": ["/private"], "regex": False}, workspace),
        lambda workspace: _read(
            {"path": "/private/marker.txt", "line_number": 1, "before": 0, "after": 0, "full": False}, workspace
        ),
    ],
)
def test_virtual_mode_denials_give_safe_next_actions(agent_workspace: Path, denied_call) -> None:
    result = denied_call(agent_workspace)
    next_step = result["next_step"].lower()

    assert result["ok"] is False
    assert "existing allowed root" in next_step
    assert "ask the host" in next_step
    assert "do not retry with path transformations" in next_step


def test_agent_access_contract_demo_shows_safe_success_and_denial() -> None:
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "examples/agent_access_contract_demo.py"],
        cwd=project_root,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["allowed_config_search"]["ok"] is True
    assert payload["allowed_config_search"]["results"][0]["path"] == "/src/backend.py"
    assert payload["private_path_denied"]["ok"] is False
    assert PRIVATE_FIXTURE_MARKER not in completed.stdout
    assert "do not retry with path transformations" in payload["safe_next_action"].lower()
