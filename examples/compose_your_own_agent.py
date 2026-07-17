"""Append PyGrepTool's read-only tools to an application-owned LangChain agent.

Run from the repository root:
    python examples\\compose_your_own_agent.py "Find Python service files under /src."
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_TORCH", "0")
os.environ.setdefault("TRANSFORMERS_NO_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from pygreptool import CodeAccessPolicy
from pygreptool.langchain_toolkit import create_pygrep_tools


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def print_tool_trace(messages: list[object]) -> None:
    """Print model-selected tool calls and safe, compact tool-result summaries."""

    for message in messages:
        for call in getattr(message, "tool_calls", []):
            print("\n--- tool call ---")
            print(f"name: {call['name']}")
            print("arguments:")
            print(json.dumps(call["args"], ensure_ascii=False, indent=2))

        if message.__class__.__name__ != "ToolMessage":
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        print("--- tool result ---")
        print(
            json.dumps(
                {
                    "tool": payload.get("tool"),
                    "ok": payload.get("ok"),
                    "summary": payload.get("summary"),
                    "count": payload.get("count"),
                    "next_step": payload.get("next_step"),
                    "error": payload.get("error"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")  # Loads the key without printing it.

    # These are the application's own tools. Add any existing web, database,
    # or business tools here; PyGrepTool does not create or own the agent.
    application_tools = []
    pygrep_tools = create_pygrep_tools(
        workspace_root=PROJECT_ROOT,
        allowed_roots=["src", "tests"],
        virtual_mode=True,
        policy=CodeAccessPolicy(),
    )
    agent = create_agent(
        model=ChatOpenAI(
            model=os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini"),
            temperature=0,
        ),
        tools=[*application_tools, *pygrep_tools],
        system_prompt=(
            "You are a concise repository assistant. "
            "Use find_files for filenames or extensions, search_code for text inside files, "
            "and read_context only when more lines are necessary. "
            "The workspace is virtual: use only paths under /src or /tests. "
            "Cite paths and line numbers from tool results."
        ),
    )
    arguments = sys.argv[1:]
    trace = "--trace" in arguments
    prompt = " ".join(argument for argument in arguments if argument != "--trace")
    prompt = prompt or "Find Python files whose names contain service under /src."
    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 12},
    )
    if trace:
        print_tool_trace(result["messages"])
        print("\n--- final answer ---")
    print(result["messages"][-1].content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
