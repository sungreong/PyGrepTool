from __future__ import annotations

import os
from pathlib import Path

import pytest


pytest.importorskip("langchain")
pytest.importorskip("langchain_openai")
pytest.importorskip("dotenv")

from pygreptool.langchain_agent import create_search_agent, load_project_env


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "agent_sample_project"


pytestmark = pytest.mark.live_agent


def _require_live_agent_env() -> None:
    if os.environ.get("RUN_LIVE_AGENT_TESTS") != "1":
        pytest.skip("set RUN_LIVE_AGENT_TESTS=1 to run live OpenAI agent tests")
    load_project_env(PROJECT_ROOT)
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not configured")


def _ask_agent(prompt: str) -> str:
    _require_live_agent_env()
    agent = create_search_agent(allowed_roots=[FIXTURE_ROOT], model_name=os.environ.get("LLM_MODEL_NAME"))
    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 10},
    )
    return result["messages"][-1].content


def test_live_agent_finds_exact_fixture_marker() -> None:
    answer = _ask_agent(
        "Find BETA_EXACT_NEEDLE in the fixture project. Answer with the file path and line number only."
    )

    assert "beta_service.py" in answer
    assert "6" in answer


def test_live_agent_recovers_from_quote_style_variant() -> None:
    answer = _ask_agent(
        "Find tests or code in the fixture project that prove backend='smart' is configured. "
        "The code may use either quote style. Answer with matching file names."
    )

    assert "alpha_service.py" in answer
    assert "beta_service.py" in answer


def test_live_agent_summarizes_pathspec_doc_marker() -> None:
    answer = _ask_agent(
        "Find documentation in the fixture project that mentions pathspec and explain in one sentence why it is optional."
    )

    assert "operations.md" in answer
    assert "optional" in answer.lower() or "not required" in answer.lower()
