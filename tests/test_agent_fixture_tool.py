from __future__ import annotations

import json
from pathlib import Path

import pytest

from pygreptool import search


pytest.importorskip("langchain_core")
pytest.importorskip("pydantic")

from pygreptool.langchain_tool import create_langchain_search_tool


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent_sample_project"


def test_fixture_tool_finds_exact_unique_code_marker() -> None:
    results = search("BETA_EXACT_NEEDLE", FIXTURE_ROOT, backend="smart", regex=False)

    assert len(results) == 1
    assert results[0].path == FIXTURE_ROOT / "src" / "beta_service.py"
    assert results[0].line_number == 6
    assert results[0].backend == "python"


def test_fixture_tool_finds_quote_variant_with_regex() -> None:
    results = search(r"[\"']?backend[\"']?\s*[:=]\s*[\"']smart[\"']", FIXTURE_ROOT, backend="smart")

    assert {result.path.name for result in results} == {"alpha_service.py", "beta_service.py"}


def test_fixture_langchain_tool_returns_json_with_precise_location() -> None:
    search_tool = create_langchain_search_tool(allowed_roots=[FIXTURE_ROOT])

    raw = search_tool.invoke(
        {
            "pattern": "RUNBOOK_DELTA_MARKER",
            "roots": [str(FIXTURE_ROOT / "docs")],
            "regex": False,
            "backend": "smart",
            "max_results": 5,
        }
    )
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["path"].endswith("operations.md")
    assert result["results"][0]["line_number"] == 3


def test_fixture_langchain_tool_resolves_relative_roots_inside_single_allowed_root() -> None:
    search_tool = create_langchain_search_tool(allowed_roots=[FIXTURE_ROOT])

    raw = search_tool.invoke(
        {
            "pattern": "BETA_EXACT_NEEDLE",
            "roots": ["src"],
            "regex": False,
            "backend": "smart",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["path"].endswith("beta_service.py")


def test_fixture_langchain_tool_enforces_allowed_roots() -> None:
    search_tool = create_langchain_search_tool(allowed_roots=[FIXTURE_ROOT / "src"])

    raw = search_tool.invoke(
        {
            "pattern": "RUNBOOK_DELTA_MARKER",
            "roots": [str(FIXTURE_ROOT / "docs")],
            "regex": False,
            "backend": "smart",
        }
    )
    result = json.loads(raw)

    assert result["ok"] is False
    assert result["error"]["type"] == "ToolInputError"


def test_fixture_python_backend_ignores_gitignored_file_when_pathspec_is_available() -> None:
    pytest.importorskip("pathspec")

    results = search("SECRET_AGENT_NEEDLE", FIXTURE_ROOT, backend="python", regex=False)

    assert results == []
