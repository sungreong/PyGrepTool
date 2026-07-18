"""Evaluate scoped code-navigation answers against a small, deterministic golden set.

This is an opt-in benchmark, not part of the default test suite. It reports two
PyGrepTool timings: direct in-process dispatch (LangChain/tool integration) and
the standalone Skill command. ``--with-codegraph`` additionally measures the
semantic queries that CodeGraph is designed to answer.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET_PATH = PROJECT_ROOT / "tests" / "fixtures" / "navigation_golden_set.json"
SKILL_RUNNER_PATH = PROJECT_ROOT / "skills" / "pygreptool-navigation" / "scripts" / "invoke_pygreptool.py"


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("pygreptool_navigation_runner", SKILL_RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load skill runner: {SKILL_RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"invalid golden set: {path}")
    return payload


def validate_result(case: Mapping[str, Any], result: Mapping[str, Any]) -> list[str]:
    """Return descriptive expectation failures for one golden case."""

    expected = case["expect"]
    failures: list[str] = []
    if result.get("ok") is not expected["ok"]:
        failures.append(f"expected ok={expected['ok']}, got {result.get('ok')}")

    if "paths" in expected:
        actual_paths = {item.get("path") for item in result.get("results", []) if isinstance(item, Mapping)}
        if set(expected["paths"]) != actual_paths:
            failures.append(f"expected paths={expected['paths']}, got {sorted(actual_paths)}")

    evidence = expected.get("evidence")
    if evidence:
        matched = any(
            item.get("path") == evidence["path"]
            and item.get("line_number") == evidence["line_number"]
            and evidence["line_contains"] in item.get("line", "")
            for item in result.get("results", [])
            if isinstance(item, Mapping)
        )
        if not matched:
            failures.append(f"missing expected evidence at {evidence['path']}:{evidence['line_number']}")

    if "path" in expected and result.get("path") != expected["path"]:
        failures.append(f"expected path={expected['path']}, got {result.get('path')}")
    for text in expected.get("content_contains", []):
        if text not in result.get("content", ""):
            failures.append(f"missing expected context text: {text}")
    if "error_type" in expected and result.get("error", {}).get("type") != expected["error_type"]:
        failures.append(f"expected error type={expected['error_type']}, got {result.get('error')}")
    return failures


def median_ms(action: Callable[[], Any], iterations: int) -> float:
    """Warm once, then return median wall-clock latency in milliseconds."""

    action()
    durations: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        action()
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
    return round(statistics.median(durations), 2)


def evaluate_pygrep_cases(golden_set: Mapping[str, Any], *, iterations: int) -> tuple[list[dict[str, Any]], dict[str, float]]:
    runner = load_runner()
    config = runner.load_project_config(PROJECT_ROOT / golden_set["config"])
    outcomes: list[dict[str, Any]] = []
    timings: dict[str, float] = {}
    for case in golden_set["cases"]:
        request = case["request"]
        result = runner.run_request(request, config)
        failures = validate_result(case, result)
        outcomes.append({"id": case["id"], "question": case["question"], "passed": not failures, "failures": failures})
        timings[case["id"]] = median_ms(lambda: runner.run_request(request, config), iterations)
    return outcomes, timings


def evaluate_skill_command(golden_set: Mapping[str, Any], *, iterations: int) -> dict[str, float]:
    config_path = PROJECT_ROOT / golden_set["config"]
    timings: dict[str, float] = {}
    for case in golden_set["cases"]:
        request = json.dumps(case["request"], ensure_ascii=False)

        def invoke() -> None:
            completed = subprocess.run(
                [sys.executable, str(SKILL_RUNNER_PATH), "--config", str(config_path), "--request", request],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(completed.stdout)
            failures = validate_result(case, payload)
            if failures:
                raise RuntimeError(f"skill command failed {case['id']}: {failures}")

        timings[case["id"]] = median_ms(invoke, iterations)
    return timings


def evaluate_journeys(golden_set: Mapping[str, Any], *, iterations: int) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Evaluate canonical multi-tool navigation plans and their total call count."""

    runner = load_runner()
    config = runner.load_project_config(PROJECT_ROOT / golden_set["config"])
    outcomes: list[dict[str, Any]] = []
    timings: dict[str, float] = {}
    for journey in golden_set.get("journeys", []):
        steps = journey["steps"]

        def invoke() -> list[str]:
            failures: list[str] = []
            for index, step in enumerate(steps, start=1):
                result = runner.run_request(step["request"], config)
                failures.extend(f"step {index}: {message}" for message in validate_result(step, result))
            return failures

        failures = invoke()
        outcomes.append(
            {
                "id": journey["id"],
                "question": journey["question"],
                "tool_calls": len(steps),
                "passed": not failures,
                "failures": failures,
            }
        )

        def measured_invoke() -> None:
            measured_failures = invoke()
            if measured_failures:
                raise RuntimeError(f"journey failed {journey['id']}: {measured_failures}")

        timings[journey["id"]] = median_ms(measured_invoke, iterations)
    return outcomes, timings


def evaluate_skill_journeys(golden_set: Mapping[str, Any], *, iterations: int) -> dict[str, float]:
    """Measure the same journeys when each selected tool is a Skill CLI call."""

    config_path = PROJECT_ROOT / golden_set["config"]
    timings: dict[str, float] = {}
    for journey in golden_set.get("journeys", []):
        steps = journey["steps"]

        def invoke() -> None:
            for index, step in enumerate(steps, start=1):
                request = json.dumps(step["request"], ensure_ascii=False)
                completed = subprocess.run(
                    [sys.executable, str(SKILL_RUNNER_PATH), "--config", str(config_path), "--request", request],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                payload = json.loads(completed.stdout)
                failures = validate_result(step, payload)
                if failures:
                    raise RuntimeError(f"skill journey failed {journey['id']} step {index}: {failures}")

        timings[journey["id"]] = median_ms(invoke, iterations)
    return timings


def evaluate_rg(golden_set: Mapping[str, Any], *, iterations: int) -> dict[str, Any]:
    query = golden_set["comparison_queries"]["rg_exact_text"]
    executable = shutil.which("rg")
    if not executable:
        return {"available": False, "reason": "rg is not installed"}
    target = PROJECT_ROOT / query["path"]
    command = [executable, "-n", "--glob", "*.py", query["pattern"], str(target)]

    def invoke() -> str:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode not in (0, 1):
            raise RuntimeError(completed.stderr.strip())
        return completed.stdout

    output = invoke()
    return {
        "available": True,
        "question": f"Find exact text {query['pattern']}",
        "median_ms": median_ms(invoke, iterations),
        "found_expected_text": query["pattern"] in output,
    }


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def codegraph_command(*args: str) -> list[str]:
    if os.name != "nt":
        return ["codegraph", *args]
    command = "& codegraph " + " ".join(_powershell_quote(arg) for arg in args)
    return ["powershell", "-NoProfile", "-Command", command]


def evaluate_codegraph(golden_set: Mapping[str, Any], *, iterations: int) -> dict[str, Any]:
    if shutil.which("codegraph") is None and os.name != "nt":
        return {"available": False, "reason": "codegraph is not installed"}
    fixture = PROJECT_ROOT / golden_set["fixture"]
    index_directory = fixture / ".codegraph"
    initialized = False
    if not index_directory.exists():
        completed = subprocess.run(codegraph_command("init", str(fixture)), capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return {"available": False, "reason": completed.stderr.strip() or completed.stdout.strip()}
        initialized = True

    def run_json(*args: str) -> Any:
        completed = subprocess.run(codegraph_command(*args), capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return json.loads(completed.stdout)

    symbol = golden_set["comparison_queries"]["codegraph_symbol"]
    callers = golden_set["comparison_queries"]["codegraph_callers"]
    symbol_result = run_json("query", symbol, "--path", str(fixture), "--json")
    callers_result = run_json("callers", callers, "--path", str(fixture), "--json")
    caller_names = {caller.get("name") for caller in callers_result.get("callers", [])}
    return {
        "available": True,
        "initialized_this_run": initialized,
        "symbol_query_median_ms": median_ms(lambda: run_json("query", symbol, "--path", str(fixture), "--json"), iterations),
        "callers_query_median_ms": median_ms(lambda: run_json("callers", callers, "--path", str(fixture), "--json"), iterations),
        "found_symbol": bool(symbol_result),
        "found_expected_caller": "build_alpha_report" in caller_names,
        "note": "CodeGraph index data stays local and is ignored by Git.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic navigation golden-set correctness and latency checks.")
    parser.add_argument("--iterations", type=int, default=7, help="Warm-query repetitions per measurement (default: 7).")
    parser.add_argument("--with-codegraph", action="store_true", help="Initialize CodeGraph if needed and measure symbol/caller queries.")
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    golden_set = load_golden_set()
    outcomes, direct_timings = evaluate_pygrep_cases(golden_set, iterations=args.iterations)
    journey_outcomes, journey_direct_timings = evaluate_journeys(golden_set, iterations=args.iterations)
    report: dict[str, Any] = {
        "golden_set": {"passed": sum(item["passed"] for item in outcomes), "total": len(outcomes), "cases": outcomes},
        "navigation_journeys": {
            "passed": sum(item["passed"] for item in journey_outcomes),
            "total": len(journey_outcomes),
            "total_tool_calls": sum(item["tool_calls"] for item in journey_outcomes),
            "average_tool_calls": round(
                sum(item["tool_calls"] for item in journey_outcomes) / len(journey_outcomes), 2
            )
            if journey_outcomes
            else 0,
            "journeys": journey_outcomes,
        },
        "latency_ms": {
            "pygreptool_in_process": direct_timings,
            "pygrepskill_command": evaluate_skill_command(golden_set, iterations=args.iterations),
            "journey_in_process": journey_direct_timings,
            "journey_skill_command": evaluate_skill_journeys(golden_set, iterations=args.iterations),
            "rg_exact_text": evaluate_rg(golden_set, iterations=args.iterations),
        },
    }
    if args.with_codegraph:
        report["latency_ms"]["codegraph_semantic"] = evaluate_codegraph(golden_set, iterations=args.iterations)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    all_golden_passed = report["golden_set"]["passed"] == report["golden_set"]["total"]
    all_journeys_passed = report["navigation_journeys"]["passed"] == report["navigation_journeys"]["total"]
    return 0 if all_golden_passed and all_journeys_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
