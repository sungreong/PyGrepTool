"""Run PyGrepTool inside a read-only mounted workspace."""

from __future__ import annotations

import json

from pygreptool import CodeAccessPolicy, run_find_files_tool


def main() -> int:
    policy = CodeAccessPolicy()
    result = run_find_files_tool(
        {
            "folder": "/src",
            "name_query": None,
            "extensions": ["py"],
            "max_results": 20,
            "hidden": False,
        },
        workspace_root="/workspace",
        allowed_roots=["src", "docs"],
        virtual_mode=True,
        policy=policy,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
