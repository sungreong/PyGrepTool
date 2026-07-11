from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("USE_TORCH", "0")
os.environ.setdefault("TRANSFORMERS_NO_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from pygreptool.langchain_agent import create_search_agent, load_project_env


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_agent():
    """Build a LangChain agent that can search this repository with pygreptool."""

    load_project_env(PROJECT_ROOT)
    return create_search_agent(allowed_roots=[PROJECT_ROOT], model_name=os.environ.get("LLM_MODEL_NAME"))


def run_prompt(prompt: str) -> str:
    agent = build_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 8},
    )
    return result["messages"][-1].content


def main() -> int:
    prompts = [
        "Where is BackendName defined, and what values can it take?",
        "Find tests that prove backend='smart' works.",
        "Find documentation that mentions pathspec and summarize why it is optional.",
    ]
    for index, prompt in enumerate(prompts, start=1):
        print(f"--- Prompt {index} ---")
        print(prompt)
        print()
        print(run_prompt(prompt))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
