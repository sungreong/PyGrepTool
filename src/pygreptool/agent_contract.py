"""Verify that an agent's access claims are backed by actual tool outcomes."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def verify_agent_access_contract(
    events: Sequence[Mapping[str, Any]],
    *,
    expected_allowed_paths: Sequence[str] = (),
    expected_denied_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Check whether required virtual paths were actually called and observed.

    ``events`` are host-recorded tool calls, not model-authored claims. Each
    event has ``tool``, ``arguments``, and the serialized tool ``result``. The
    verifier intentionally does not infer access from a final natural-language
    answer: a required path is verified only when an exact matching Tool call
    produced the expected ``ok`` result.
    """

    checks = [
        _check_path(events, path=path, expected="allowed") for path in expected_allowed_paths
    ] + [
        _check_path(events, path=path, expected="denied") for path in expected_denied_paths
    ]
    verified = all(check["status"] == "passed" for check in checks)
    return {
        "verified": verified,
        "checks": checks,
        "next_step": (
            "All required access checks are backed by observed tool results."
            if verified
            else (
                "Do not treat the final answer as verified for unobserved paths. "
                "Run the missing scoped tool call or correct the requested access contract."
            )
        ),
    }


def _check_path(events: Sequence[Mapping[str, Any]], *, path: str, expected: str) -> dict[str, Any]:
    attempts = [event for event in events if path in _agent_paths_for_event(event)]
    observed = [
        {"tool": event.get("tool"), "ok": _result_ok(event)}
        for event in attempts
    ]
    if not attempts:
        status = "not_checked"
    elif expected == "allowed":
        status = "passed" if any(_result_ok(event) is True for event in attempts) else "unexpected_denial"
    else:
        status = "passed" if any(_result_ok(event) is False for event in attempts) else "unexpected_access"
    return {
        "path": path,
        "expected": expected,
        "status": status,
        "observed": observed,
    }


def _agent_paths_for_event(event: Mapping[str, Any]) -> list[str]:
    arguments = event.get("arguments")
    if not isinstance(arguments, Mapping):
        return []
    paths: list[str] = []
    roots = arguments.get("roots")
    if isinstance(roots, Sequence) and not isinstance(roots, str):
        paths.extend(item for item in roots if isinstance(item, str))
    for field in ("folder", "path"):
        value = arguments.get(field)
        if isinstance(value, str):
            paths.append(value)
    return paths


def _result_ok(event: Mapping[str, Any]) -> bool | None:
    result = event.get("result")
    return result.get("ok") if isinstance(result, Mapping) and isinstance(result.get("ok"), bool) else None
