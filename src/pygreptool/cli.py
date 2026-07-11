from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from pygreptool.core import BackendName, SearchBackendError, SearchResult, search


def _result_to_dict(result: SearchResult) -> dict[str, object]:
    data = asdict(result)
    data["path"] = str(result.path)
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pygreptool",
        description="Search files using rg/grep first, then pure Python fallback.",
    )
    parser.add_argument("pattern", help="Text or regex pattern to search for.")
    parser.add_argument(
        "roots",
        nargs="*",
        default=["."],
        help="Files or directories to search. Defaults to current directory.",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "smart", "rg", "grep", "python"],
        default="auto",
        help="Search backend to use. smart avoids external process overhead for small roots. Default: auto.",
    )
    parser.add_argument(
        "--fixed",
        action="store_true",
        help="Treat pattern as a fixed string, not a regex.",
    )
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        help="Case-insensitive search.",
    )
    parser.add_argument(
        "-g",
        "--glob",
        action="append",
        dest="include",
        help="Include glob. Can be repeated. Example: -g '*.py'",
    )
    parser.add_argument(
        "--hidden",
        action="store_true",
        help="Include hidden files/directories when supported.",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="In auto mode, fail instead of trying the next backend after an error.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding for Python backend and grep output. Default: utf-8.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum number of results to print.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON object per result.",
    )
    return parser


def _print_text_result(result: SearchResult) -> None:
    column = "" if result.column is None else f":{result.column}"
    print(f"{result.path}:{result.line_number}{column}:{result.line}")


def _print_json_result(result: SearchResult) -> None:
    print(json.dumps(_result_to_dict(result), ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        results = search(
            args.pattern,
            [Path(root) for root in args.roots],
            regex=not args.fixed,
            include=args.include,
            ignore_case=args.ignore_case,
            hidden=args.hidden,
            backend=args.backend,  # type: ignore[arg-type]
            fallback=not args.no_fallback,
            encoding=args.encoding,
            max_results=args.max_results,
        )
    except (SearchBackendError, OSError, ValueError) as exc:
        print(f"pygreptool: {exc}", file=sys.stderr)
        return 2

    printer = _print_json_result if args.json else _print_text_result
    for result in results:
        printer(result)

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
