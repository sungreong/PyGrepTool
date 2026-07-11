from __future__ import annotations

import json
from pathlib import Path

from pygreptool import search_code_tool

arguments = {
    "pattern": "TODO",
    "roots": ["examples"],
    "regex": False,
    "include": ["*.py", "*.md"],
    "ignore_case": False,
    "hidden": False,
    "backend": "auto",
    "fallback": True,
    "encoding": "utf-8",
    "max_results": 20,
}

result = search_code_tool(arguments, allowed_roots=[Path.cwd()])
print(json.dumps(result, ensure_ascii=False, indent=2))
