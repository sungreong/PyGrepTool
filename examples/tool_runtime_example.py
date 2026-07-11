from __future__ import annotations

import json

from pygreptool.tool import get_openai_responses_tool_schema, run_search_tool


if __name__ == "__main__":
    print("# Tool schema name")
    print(get_openai_responses_tool_schema()["name"])

    # This is the same JSON-like argument object an LLM tool call would produce.
    arguments = {
        "pattern": "TODO",
        "roots": ["examples"],
        "regex": False,
        "include": ["*.py", "*.md"],
        "ignore_case": None,
        "hidden": None,
        "backend": "auto",
        "fallback": None,
        "encoding": None,
        "max_results": 20,
        "max_line_chars": 300,
    }

    result = run_search_tool(arguments, allowed_roots=["."])
    print(json.dumps(result, ensure_ascii=False, indent=2))
