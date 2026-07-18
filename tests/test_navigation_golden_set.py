from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_PATH = PROJECT_ROOT / "scripts" / "evaluate_navigation.py"


def load_evaluator():
    spec = importlib.util.spec_from_file_location("pygreptool_navigation_evaluator", EVALUATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_navigation_golden_set_returns_expected_evidence_and_policy_denials() -> None:
    evaluator = load_evaluator()
    golden_set = evaluator.load_golden_set()

    outcomes, _ = evaluator.evaluate_pygrep_cases(golden_set, iterations=1)

    assert len(outcomes) == 4
    assert all(outcome["passed"] for outcome in outcomes), outcomes


def test_navigation_journeys_use_the_expected_number_of_tool_calls() -> None:
    evaluator = load_evaluator()
    golden_set = evaluator.load_golden_set()

    outcomes, _ = evaluator.evaluate_journeys(golden_set, iterations=1)

    assert len(outcomes) == 6
    assert sum(outcome["tool_calls"] for outcome in outcomes) == 8
    assert all(outcome["passed"] for outcome in outcomes), outcomes
