from __future__ import annotations

import os
from pathlib import Path

import pytest


pytest.importorskip("langchain")
pytest.importorskip("langchain_openai")
dotenv = pytest.importorskip("dotenv")

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from pygreptool import CodeAccessPolicy
from pygreptool.langchain_toolkit import create_pygrep_tools


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "agent_sample_project"

pytestmark = pytest.mark.live_agent

SYSTEM_PROMPT = (
    "You are a concise code-navigation assistant. "
    "Use find_files for filenames, folders, or extensions; search_code for text or symbols inside files; "
    "and read_context only when more lines are needed. "
    "Use roots ['.'] unless the user named a folder or find_files returned one. "
    "For quote or spacing variants, use a regex that accepts a closing key quote, for example "
    "backend['\"]?\\s*[:=]\\s*['\"]smart['\"]. "
    "Report every requested match. Every search-based final answer must include a returned path and line number."
)


def _require_live_agent_env() -> None:
    dotenv.load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.fail("OPENAI_API_KEY is required because live-agent tests run in the default pytest suite")


def _ask_agent(prompt: str, *, virtual_mode: bool = False):
    _require_live_agent_env()
    agent = create_agent(
        model=ChatOpenAI(model=os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini"), temperature=0),
        tools=create_pygrep_tools(
            workspace_root=FIXTURE_ROOT,
            allowed_roots=["."],
            virtual_mode=virtual_mode,
            policy=CodeAccessPolicy(),
        ),
        system_prompt=SYSTEM_PROMPT,
    )
    return agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 20},
    )


def test_live_agent_finds_exact_fixture_marker() -> None:
    result = _ask_agent("Find BETA_EXACT_NEEDLE in the fixture project. Answer with the file path and line number only.")
    answer = result["messages"][-1].content

    assert "beta_service.py" in answer
    assert "6" in answer


def test_live_agent_recovers_from_quote_style_variant() -> None:
    result = _ask_agent(
        "Find tests or code in the fixture project that prove backend='smart' is configured. "
        "The code may use either quote style. Answer with matching file names."
    )
    answer = result["messages"][-1].content

    assert "alpha_service.py" in answer
    assert "beta_service.py" in answer


def test_live_agent_summarizes_pathspec_doc_marker() -> None:
    result = _ask_agent(
        "Find documentation in the fixture project that mentions pathspec and explain in one sentence why it is optional."
    )
    answer = result["messages"][-1].content

    assert "operations.md" in answer
    assert "optional" in answer.lower() or "not required" in answer.lower()


def test_live_agent_uses_find_files_for_scoped_extension_request() -> None:
    result = _ask_agent(
        "In the fixture project, find Python files in src whose filenames contain service. Return the matching file paths only."
    )

    tool_messages = [message for message in result["messages"] if message.__class__.__name__ == "ToolMessage"]
    answer = result["messages"][-1].content
    assert "find_files" in [message.name for message in tool_messages]
    assert "alpha_service.py" in answer
    assert "beta_service.py" in answer


def test_live_agent_uses_virtual_paths_without_host_path_disclosure() -> None:
    result = _ask_agent(
        "Find Python files whose names contain service under /src. Return the matching virtual file paths only.",
        virtual_mode=True,
    )

    tool_messages = [message for message in result["messages"] if message.__class__.__name__ == "ToolMessage"]
    answer = result["messages"][-1].content
    assert "find_files" in [message.name for message in tool_messages]
    assert "/src/alpha_service.py" in answer
    assert "/src/beta_service.py" in answer
    assert str(FIXTURE_ROOT) not in answer
