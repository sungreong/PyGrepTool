from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest


os.environ.setdefault("USE_TORCH", "0")
os.environ.setdefault("TRANSFORMERS_NO_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

pytest.importorskip("langchain")
pytest.importorskip("langchain_core")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from pygreptool.langchain_agent import create_search_agent


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent_sample_project"


class ToolCallingFakeModel(FakeMessagesListChatModel):
    """Fake chat model that supports the tool binding LangChain agents require."""

    def bind_tools(self, tools: list[Any], *, tool_choice: str | None = None, **kwargs: Any):  # type: ignore[no-untyped-def]
        return self


def test_agent_uses_search_code_then_read_context() -> None:
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
                            "context_before": 1,
                            "context_after": 1,
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
            AIMessage(
                content=(
                    "src/beta_service.py:6 contains BETA_EXACT_NEEDLE, and the wider "
                    "context shows configure_beta uses backend smart."
                )
            ),
        ]
    )
    agent = create_search_agent(
        model=model,
        workspace_root=FIXTURE_ROOT,
        allowed_roots=["src"],
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Find BETA_EXACT_NEEDLE and inspect its surrounding context."}]},
        config={"recursion_limit": 10},
    )

    tool_messages = [message for message in result["messages"] if message.__class__.__name__ == "ToolMessage"]
    assert [message.name for message in tool_messages] == ["search_code", "read_context"]
    assert "read_context_args" in tool_messages[0].content
    assert "configure_beta" in tool_messages[1].content
    assert "content" in tool_messages[1].content
    assert result["messages"][-1].content.startswith("src/beta_service.py:6")
