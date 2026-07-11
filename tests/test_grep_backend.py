from __future__ import annotations

from pathlib import Path

import pytest

from pygreptool import search
from pygreptool.backends.grep import grep_available


pytestmark = pytest.mark.skipif(not grep_available(), reason="grep is not installed")


def test_grep_backend_finds_match(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("alpha\nTODO: from grep\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="grep", regex=False)

    assert len(results) == 1
    assert results[0].path == target
    assert results[0].line_number == 2
    assert results[0].column == 1
    assert results[0].match == "TODO"
    assert results[0].backend == "grep"
