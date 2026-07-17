from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


pytest.importorskip("langchain")
pytest.importorskip("langchain_core")

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from pygreptool.langchain_toolkit import create_pygrep_tools


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent_sample_project"


class ToolCallingFakeModel(FakeMessagesListChatModel):
    """Fake chat model that supports the tool binding LangChain agents require."""

    def bind_tools(self, tools: list[Any], *, tool_choice: str | None = None, **kwargs: Any):  # type: ignore[no-untyped-def]
        return self


def test_application_owned_agent_uses_search_then_read_context() -> None:
    target = FIXTURE_ROOT / "src" / "beta_service.py"
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_code",
                        "args": {
                            "pattern": "BETA_EXACT_NEEDLE",
                            "roots": ["src"],
                            "regex": False,
                            "backend": "smart",
                            "max_results": 5,
                            "include_context": False,
                        },
                        "id": "call_search",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_context",
                        "args": {
                            "path": str(target),
                            "line_number": 6,
                            "before": 5,
                            "after": 0,
                            "full": False,
                            "max_lines": 20,
                            "max_chars": 20000,
                            "encoding": "utf-8",
                        },
                        "id": "call_read_context",
                    }
                ],
            ),
            AIMessage(content="src/beta_service.py:6 contains BETA_EXACT_NEEDLE."),
        ]
    )
    agent = create_agent(
        model=model,
        tools=create_pygrep_tools(workspace_root=FIXTURE_ROOT, allowed_roots=["src"]),
        system_prompt="Use the supplied read-only tools to inspect code.",
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Find BETA_EXACT_NEEDLE and inspect its surrounding context."}]},
        config={"recursion_limit": 10},
    )

    tool_messages = [message for message in result["messages"] if message.__class__.__name__ == "ToolMessage"]
    assert [message.name for message in tool_messages] == ["search_code", "read_context"]
    assert "read_context_args" in tool_messages[0].content
    assert "configure_beta" in tool_messages[1].content
    assert result["messages"][-1].content.startswith("src/beta_service.py:6")


def test_application_owned_agent_can_use_file_discovery() -> None:
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "find_files",
                        "args": {"folder": "src", "name_query": "service", "extensions": ["py"]},
                        "id": "call_find",
                    }
                ],
            ),
            AIMessage(content="The matching Python files are alpha_service.py and beta_service.py."),
        ]
    )
    agent = create_agent(
        model=model,
        tools=create_pygrep_tools(workspace_root=FIXTURE_ROOT, allowed_roots=["src"]),
        system_prompt="Use the supplied read-only tools to inspect code.",
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Find Python service files in src."}]},
        config={"recursion_limit": 6},
    )

    tool_messages = [message for message in result["messages"] if message.__class__.__name__ == "ToolMessage"]
    assert [message.name for message in tool_messages] == ["find_files"]
    assert "alpha_service.py" in tool_messages[0].content
    assert "beta_service.py" in tool_messages[0].content
