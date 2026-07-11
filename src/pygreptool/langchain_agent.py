from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("USE_TORCH", "0")
os.environ.setdefault("TRANSFORMERS_NO_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from pygreptool.langchain_tool import create_langchain_read_context_tool, create_langchain_search_tool


DEFAULT_AGENT_SYSTEM_PROMPT = (
    "You are a concise code-search assistant. "
    "When the user asks where code, tests, docs, TODOs, imports, or symbols are, "
    "call search_code before answering. Prefer focused roots such as ['src'], ['tests'], "
    "or ['docs']; use backend='smart' unless the user asks for a specific backend. "
    "If an exact phrase search returns no results, retry with a shorter token or a regex "
    "that handles single-quote/double-quote, spacing, ':' and '=' variants, for example "
    "[\"']?key[\"']?\\s*[:=]\\s*[\"']value[\"']. If the user asks for files, matches, "
    "or examples in plural, return all relevant matches from the tool result, not only the first. Never conclude that "
    "a symbol or option is absent after only one failed exact search. "
    "Cite file paths and line numbers from tool results. "
    "If the search result does not provide enough surrounding code, call read_context "
    "with the result's read_context_args before answering."
)


def load_project_env(project_root: str | os.PathLike[str]) -> None:
    """Load a project .env file without exposing its contents."""

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise ImportError("Agent examples require python-dotenv. Install pygreptool[agent].") from exc

    load_dotenv(Path(project_root) / ".env")


def create_search_agent(
    *,
    allowed_roots: Sequence[str | os.PathLike[str]],
    workspace_root: str | os.PathLike[str] | None = None,
    model: Any | None = None,
    model_name: str | None = None,
    temperature: float = 0,
    system_prompt: str = DEFAULT_AGENT_SYSTEM_PROMPT,
    include_read_context: bool = True,
):
    """Create a LangChain agent wired to the pygreptool search_code tool."""

    try:
        from langchain.agents import create_agent
    except ImportError as exc:
        raise ImportError("Agent integration requires pygreptool[agent] dependencies.") from exc

    if model is None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ImportError("Default agent model requires langchain-openai. Install pygreptool[agent].") from exc
        model = ChatOpenAI(model=model_name or os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini"), temperature=temperature)

    tools = [
        create_langchain_search_tool(workspace_root=workspace_root, allowed_roots=allowed_roots),
    ]
    if include_read_context:
        tools.append(create_langchain_read_context_tool(workspace_root=workspace_root, allowed_roots=allowed_roots))

    return create_agent(model=model, tools=tools, system_prompt=system_prompt)
