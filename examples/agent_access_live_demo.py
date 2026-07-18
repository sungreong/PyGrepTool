"""Run a live LangChain agent against a read-only, policy-bound workspace.

Use through Docker Compose so only the fixture workspace is mounted:
    docker compose --profile live-agent run --rm agent-live-demo
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from pygreptool import CodeAccessPolicy
from pygreptool.agent_contract import verify_agent_access_contract
from pygreptool.langchain_toolkit import create_pygrep_tools


def _safe_trace(messages: list[Any]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Keep the demonstration trace useful without echoing arbitrary tool input."""

    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    events_by_call_id: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for message in messages:
        for call in getattr(message, "tool_calls", []):
            arguments = call.get("args", {})
            event = {"tool": call.get("name"), "arguments": arguments, "result": None}
            events.append(event)
            call_id = call.get("id")
            if isinstance(call_id, str):
                events_by_call_id[call_id] = event
            tool_calls.append(
                {
                    "name": call.get("name"),
                    "roots": arguments.get("roots"),
                    "folder": arguments.get("folder"),
                    "path": arguments.get("path"),
                    "pattern_supplied": "pattern" in arguments,
                }
            )
        if message.__class__.__name__ != "ToolMessage":
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        tool_call_id = getattr(message, "tool_call_id", None)
        if isinstance(tool_call_id, str) and tool_call_id in events_by_call_id:
            events_by_call_id[tool_call_id]["result"] = payload
        tool_results.append(
            {
                "tool": payload.get("tool"),
                "ok": payload.get("ok"),
                "summary": payload.get("summary"),
                "count": payload.get("count"),
                "next_step": payload.get("next_step"),
                "error": payload.get("error"),
            }
        )
    return {"tool_calls": tool_calls, "tool_results": tool_results}, events


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY must be provided through the environment.")

    tools = create_pygrep_tools(
        workspace_root="/workspace",
        allowed_roots=["src", "docs"],
        virtual_mode=True,
        policy=CodeAccessPolicy(),
    )
    agent = create_agent(
        model=ChatOpenAI(model=os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini"), temperature=0),
        tools=tools,
        system_prompt=(
            "You are a concise, read-only code-navigation assistant. "
            "Use find_files for filename or extension questions, search_code for text inside files, "
            "and read_context only when more surrounding lines are needed. "
            "The workspace is virtual and only /src and /docs are allowed. "
            "Never use path transformations to work around a denied request. "
            "When a request is denied, state the tool's safe next_step instead of inferring or revealing protected content. "
            "Always write the final answer in Korean."
        ),
    )
    arguments = sys.argv[1:]
    expected_allowed_paths: list[str] = []
    expected_denied_paths: list[str] = []
    prompt_parts: list[str] = []
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option == "--expect-allowed" and index + 1 < len(arguments):
            expected_allowed_paths.append(arguments[index + 1])
            index += 2
            continue
        if option == "--expect-denied" and index + 1 < len(arguments):
            expected_denied_paths.append(arguments[index + 1])
            index += 2
            continue
        prompt_parts.append(option)
        index += 1

    default_prompt = not prompt_parts
    prompt = " ".join(prompt_parts).strip() or (
        "Find BACKEND_MODE under /src, then make one harmless search for marker under /private "
        "to demonstrate the policy denial and its safe next action."
    )
    if default_prompt:
        expected_allowed_paths = expected_allowed_paths or ["/src"]
        expected_denied_paths = expected_denied_paths or ["/private"]
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        },
        config={"recursion_limit": 8},
    )
    trace, events = _safe_trace(result["messages"])
    contract = verify_agent_access_contract(
        events,
        expected_allowed_paths=expected_allowed_paths,
        expected_denied_paths=expected_denied_paths,
    )
    print(json.dumps({**trace, "access_contract": contract}, ensure_ascii=False, indent=2))
    print("\n--- 최종 답변 ---")
    print(result["messages"][-1].content)
    return 0 if contract["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
