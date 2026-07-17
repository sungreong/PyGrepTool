from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


pytest.importorskip("dotenv")
pytest.importorskip("langchain")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PATH = PROJECT_ROOT / "examples" / "compose_your_own_agent.py"


def _load_example_module():
    spec = importlib.util.spec_from_file_location("compose_your_own_agent", EXAMPLE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_trace_prints_tool_arguments_and_result_summary(capsys) -> None:  # type: ignore[no-untyped-def]
    module = _load_example_module()

    class AIMessage:
        tool_calls = [{"name": "search_code", "args": {"pattern": "TODO", "roots": ["/src"]}}]

    class ToolMessage:
        content = '{"tool":"search_code","ok":true,"count":1,"summary":"Found 1 match.","error":null}'

    module.print_tool_trace([AIMessage(), ToolMessage()])

    output = capsys.readouterr().out
    assert "--- tool call ---" in output
    assert '"pattern": "TODO"' in output
    assert "--- tool result ---" in output
    assert '"count": 1' in output
