from __future__ import annotations

from pygreptool import verify_agent_access_contract


def test_access_contract_passes_only_with_observed_allowed_and_denied_calls() -> None:
    contract = verify_agent_access_contract(
        [
            {"tool": "search_code", "arguments": {"roots": ["/src"]}, "result": {"ok": True}},
            {"tool": "find_files", "arguments": {"folder": "/private"}, "result": {"ok": False}},
        ],
        expected_allowed_paths=["/src"],
        expected_denied_paths=["/private"],
    )

    assert contract["verified"] is True
    assert [check["status"] for check in contract["checks"]] == ["passed", "passed"]


def test_access_contract_rejects_a_final_claim_when_private_path_was_not_called() -> None:
    contract = verify_agent_access_contract(
        [
            {"tool": "search_code", "arguments": {"roots": ["/src"]}, "result": {"ok": True}},
            {"tool": "find_files", "arguments": {"folder": "src"}, "result": {"ok": True}},
        ],
        expected_allowed_paths=["/src"],
        expected_denied_paths=["/private"],
    )

    assert contract["verified"] is False
    assert contract["checks"][1]["status"] == "not_checked"
    assert "Do not treat the final answer as verified" in contract["next_step"]
