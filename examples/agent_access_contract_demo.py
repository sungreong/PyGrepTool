"""Show the safe success-and-denial contract returned to a code-navigation agent."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pygreptool import CodeAccessPolicy, run_search_tool


PRIVATE_FIXTURE_MARKER = "HARMLESS_PRIVATE_DEMO_MARKER"


def main() -> int:
    with TemporaryDirectory(prefix="pygreptool-agent-access-") as temporary_directory:
        workspace = Path(temporary_directory)
        src = workspace / "src"
        private = workspace / "private"
        src.mkdir()
        private.mkdir()
        (src / "backend.py").write_text("BACKEND_MODE = 'demo'\n", encoding="utf-8")
        (private / "marker.txt").write_text(f"{PRIVATE_FIXTURE_MARKER}\n", encoding="utf-8")

        common = {
            "workspace_root": workspace,
            "allowed_roots": ["src"],
            "virtual_mode": True,
            "policy": CodeAccessPolicy(),
        }
        allowed_search = run_search_tool(
            {
                "pattern": "BACKEND_MODE",
                "roots": ["/src"],
                "regex": False,
                "context_before": 0,
                "context_after": 0,
            },
            **common,
        )
        denied_private_search = run_search_tool(
            {"pattern": PRIVATE_FIXTURE_MARKER, "roots": ["/private"], "regex": False},
            **common,
        )

        payload = {
            "allowed_config_search": allowed_search,
            "private_path_denied": denied_private_search,
            "safe_next_action": denied_private_search["next_step"],
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        assert allowed_search["ok"] is True
        assert denied_private_search["ok"] is False
        assert PRIVATE_FIXTURE_MARKER not in rendered
        assert str(workspace) not in rendered
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
