from __future__ import annotations

from pathlib import Path

import pytest

from pygreptool import search
from pygreptool.backends.rg import rg_available


pytestmark = pytest.mark.skipif(not rg_available(), reason="ripgrep is not installed")


def test_rg_backend_finds_match(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("alpha\nTODO: from rg\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="rg", regex=False)

    assert len(results) == 1
    assert results[0].path == target
    assert results[0].line_number == 2
    assert results[0].column == 1
    assert results[0].match == "TODO"
    assert results[0].backend == "rg"


def test_rg_backend_supports_unicode_column(tmp_path: Path) -> None:
    target = tmp_path / "unicode.txt"
    target.write_text("가나다 TODO\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="rg", regex=False)

    assert len(results) == 1
    assert results[0].column == 5
