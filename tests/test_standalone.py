from __future__ import annotations

from pathlib import Path

import pytest

from standalone.pygrep_tool import search_files


def test_standalone_search_is_copy_paste_ready(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("alpha\nTODO: improve\nomega\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("TODO docs\n", encoding="utf-8")

    hits = search_files("TODO", tmp_path, include=["*.py"])

    assert len(hits) == 1
    assert hits[0].line_number == 2
    assert hits[0].column == 1
    assert hits[0].match == "TODO"
    assert "1: alpha" in hits[0].context
    assert hits[0].to_dict()["line"] == "TODO: improve"


def test_standalone_search_supports_regex_and_limit(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("class UserService:\nclass OrderService:\n", encoding="utf-8")

    hits = search_files(r"class \w+Service", tmp_path, regex=True, max_results=1)

    assert [hit.match for hit in hits] == ["class UserService"]
    assert search_files("class", tmp_path, max_results=0) == []


def test_standalone_search_enforces_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()

    with pytest.raises(ValueError, match="outside allowed_roots"):
        search_files("secret", outside, allowed_roots=[allowed])
