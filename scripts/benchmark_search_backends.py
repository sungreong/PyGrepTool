from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pygreptool import SearchBackendError, search
from pygreptool.backends.python import iter_candidate_files


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    pattern: str
    roots: tuple[str, ...]
    regex: bool
    include: tuple[str, ...] | None = None


CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        name="single_file_symbol",
        pattern="search_code",
        roots=("src/pygreptool/tool.py",),
        regex=False,
    ),
    BenchmarkCase(
        name="docs_optional_dependency",
        pattern="pathspec",
        roots=("docs",),
        regex=False,
        include=("*.md",),
    ),
    BenchmarkCase(
        name="src_regex_functions",
        pattern=r"def search_with_",
        roots=("src",),
        regex=True,
        include=("*.py",),
    ),
    BenchmarkCase(
        name="repo_backend_keyword",
        pattern="backend",
        roots=("src", "tests", "docs", "examples"),
        regex=False,
        include=("*.py", "*.md"),
    ),
)

BACKENDS: tuple[str, ...] = ("python", "rg", "smart", "auto", "grep")


def count_candidate_files(case: BenchmarkCase) -> int:
    roots = [PROJECT_ROOT / root for root in case.roots]
    include = list(case.include) if case.include is not None else None
    return sum(1 for _ in iter_candidate_files(roots, include=include, hidden=False))


def run_case(case: BenchmarkCase, backend: str, repeats: int) -> dict[str, Any]:
    roots = [str(PROJECT_ROOT / root) for root in case.roots]
    include = list(case.include) if case.include is not None else None
    candidate_files = count_candidate_files(case)

    timings_ms: list[float] = []
    match_count = 0
    matched_files = 0
    result_backends: list[str] = []

    try:
        for _ in range(repeats):
            started = time.perf_counter_ns()
            results = search(
                case.pattern,
                roots,
                regex=case.regex,
                include=include,
                backend=backend,  # type: ignore[arg-type]
                fallback=True,
            )
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            timings_ms.append(elapsed_ms)

            if not match_count:
                match_count = len(results)
                matched_files = len({str(item.path) for item in results})
                result_backends = sorted({item.backend for item in results})
    except (SearchBackendError, FileNotFoundError, ValueError) as exc:
        return {
            "backend": backend,
            "available": False,
            "error": str(exc),
            "candidate_files": candidate_files,
        }

    return {
        "backend": backend,
        "available": True,
        "candidate_files": candidate_files,
        "match_count": match_count,
        "matched_files": matched_files,
        "result_backends": result_backends,
        "runs_ms": [round(value, 3) for value in timings_ms],
        "median_ms": round(statistics.median(timings_ms), 3),
        "min_ms": round(min(timings_ms), 3),
        "max_ms": round(max(timings_ms), 3),
    }


def benchmark(repeats: int) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for case in CASES:
        case_result = asdict(case)
        case_result["results"] = [run_case(case, backend, repeats) for backend in BACKENDS]
        cases.append(case_result)
    return {"repeats": repeats, "cases": cases}


def to_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Search Backend Benchmark",
        "",
        f"- Date: {time.strftime('%Y-%m-%d')}",
        f"- Repeats per backend: {payload['repeats']}",
        "- Measured target: raw `search()` backend speed only",
        "- Environment note: this host has `rg`; `grep` is not installed",
        "",
    ]

    for case in payload["cases"]:
        include = ", ".join(case["include"]) if case["include"] else "(none)"
        lines.extend(
            [
                f"## {case['name']}",
                "",
                f"- Pattern: `{case['pattern']}`",
                f"- Regex: `{case['regex']}`",
                f"- Roots: `{', '.join(case['roots'])}`",
                f"- Include: `{include}`",
                "",
                "| Backend | Available | Candidate files | Matched files | Match count | Median ms | Notes |",
                "| --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for result in case["results"]:
            if not result["available"]:
                lines.append(
                    f"| `{result['backend']}` | no | {result['candidate_files']} | - | - | - | {result['error']} |"
                )
                continue
            notes = ", ".join(result["result_backends"]) if result["result_backends"] else "no matches"
            lines.append(
                f"| `{result['backend']}` | yes | {result['candidate_files']} | {result['matched_files']} | "
                f"{result['match_count']} | {result['median_ms']} | {notes} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark pygreptool search backends.")
    parser.add_argument("--repeats", type=int, default=7, help="Number of runs per case/backend.")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format.",
    )
    args = parser.parse_args()

    payload = benchmark(args.repeats)
    if args.format == "markdown":
        print(to_markdown(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
