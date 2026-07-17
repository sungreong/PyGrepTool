from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .tool import (
    allowed_roots_from_env,
    get_openai_chat_tool_schema,
    get_openai_responses_tool_schema,
    run_search_tool,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pygrep-tool",
        description="Print pygreptool function-tool schemas or execute the search_code tool with JSON arguments.",
    )
    parser.add_argument(
        "--schema",
        choices=["responses", "chat", "both"],
        help="Print the OpenAI-style tool schema and exit.",
    )
    parser.add_argument(
        "--call",
        nargs="?",
        const="-",
        metavar="JSON_OR_FILE",
        help=(
            "Execute the tool. Omit the value or pass '-' to read JSON arguments from stdin. "
            "If the value points to an existing file, the file is read; otherwise the value is parsed as JSON."
        ),
    )
    parser.add_argument(
        "--allowed-root",
        action="append",
        default=None,
        help=(
            "Restrict searchable roots. Can be repeated. If omitted, PYGREPKIT_ALLOWED_ROOTS "
            "is used when present."
        ),
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    return parser


def _dump_json(payload: Any, *, pretty: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


def _read_json_argument(source: str) -> str:
    if source == "-":
        return sys.stdin.read()

    candidate = Path(source)
    if candidate.exists() and candidate.is_file():
        return candidate.read_text(encoding="utf-8")

    return source


def _schema_payload(kind: str) -> Any:
    if kind == "responses":
        return get_openai_responses_tool_schema()
    if kind == "chat":
        return get_openai_chat_tool_schema()
    return {
        "responses": get_openai_responses_tool_schema(),
        "chat": get_openai_chat_tool_schema(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.schema:
        _dump_json(_schema_payload(args.schema), pretty=args.pretty)
        return 0

    if args.call is not None:
        raw_json = _read_json_argument(args.call)
        allowed_roots = args.allowed_root if args.allowed_root is not None else allowed_roots_from_env()
        result = run_search_tool(raw_json, allowed_roots=allowed_roots)
        _dump_json(result, pretty=args.pretty)
        return 0 if result.get("ok") else 1

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
