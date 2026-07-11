from __future__ import annotations

import json
from pathlib import Path

from pygreptool import cli


def test_cli_text_output(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "app.py"
    target.write_text("TODO from cli\n", encoding="utf-8")

    exit_code = cli.main(["TODO", str(tmp_path), "--backend", "python", "--fixed"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "app.py:1:1:TODO from cli" in captured.out


def test_cli_json_output(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "app.py"
    target.write_text("TODO from cli\n", encoding="utf-8")

    exit_code = cli.main(["TODO", str(tmp_path), "--backend", "python", "--fixed", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["path"].endswith("app.py")
    assert payload["line_number"] == 1
    assert payload["column"] == 1
    assert payload["match"] == "TODO"


def test_cli_no_match_exit_code_is_one(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "app.py"
    target.write_text("nothing here\n", encoding="utf-8")

    exit_code = cli.main(["TODO", str(tmp_path), "--backend", "python", "--fixed"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
