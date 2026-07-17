"""Run a local, key-free check of filename discovery and virtual paths."""

from __future__ import annotations

import json
from pathlib import Path

from pygreptool import CodeAccessPolicy, run_find_files_tool


def main() -> int:
    workspace = Path(__file__).with_name("sample_project")
    result = run_find_files_tool(
        {"folder": "/", "extensions": ["py"], "max_results": 20},
        workspace_root=workspace,
        allowed_roots=["."],
        virtual_mode=True,
        policy=CodeAccessPolicy(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
