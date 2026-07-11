from __future__ import annotations

from pathlib import Path

import pytest

from pygreptool import search


def test_python_backend_finds_fixed_string_with_line_and_column(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("alpha\nTODO: first\nprint('done')\n", encoding="utf-8")

    results = search("TODO", target, backend="python", regex=False)

    assert len(results) == 1
    assert results[0].path == target
    assert results[0].line_number == 2
    assert results[0].column == 1
    assert results[0].line == "TODO: first"
    assert results[0].match == "TODO"
    assert results[0].backend == "python"


def test_python_backend_finds_regex_matches(tmp_path: Path) -> None:
    target = tmp_path / "service.py"
    target.write_text("class UserService:\nclass OrderService:\n", encoding="utf-8")

    results = search(r"class \w+Service", tmp_path, backend="python")

    assert [result.line_number for result in results] == [1, 2]
    assert [result.match for result in results] == ["class UserService", "class OrderService"]


def test_python_backend_include_glob(tmp_path: Path) -> None:
    py_file = tmp_path / "app.py"
    md_file = tmp_path / "notes.md"
    py_file.write_text("TODO in python\n", encoding="utf-8")
    md_file.write_text("TODO in markdown\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="python", regex=False, include=["*.py"])

    assert len(results) == 1
    assert results[0].path == py_file


def test_python_backend_skips_binary_file(tmp_path: Path) -> None:
    text_file = tmp_path / "readme.txt"
    binary_file = tmp_path / "image.bin"
    text_file.write_text("TODO in text\n", encoding="utf-8")
    binary_file.write_bytes(b"\x00TODO\x00")

    results = search("TODO", tmp_path, backend="python", regex=False)

    assert len(results) == 1
    assert results[0].path == text_file


def test_python_backend_hidden_file_is_skipped_by_default(tmp_path: Path) -> None:
    visible = tmp_path / "visible.txt"
    hidden = tmp_path / ".hidden.txt"
    visible.write_text("TODO visible\n", encoding="utf-8")
    hidden.write_text("TODO hidden\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="python", regex=False)

    assert [result.path for result in results] == [visible]


def test_python_backend_hidden_file_can_be_included(tmp_path: Path) -> None:
    visible = tmp_path / "visible.txt"
    hidden = tmp_path / ".hidden.txt"
    visible.write_text("TODO visible\n", encoding="utf-8")
    hidden.write_text("TODO hidden\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="python", regex=False, hidden=True)

    assert {result.path.name for result in results} == {"visible.txt", ".hidden.txt"}


def test_python_backend_uses_pathspec_gitignore_when_available(tmp_path: Path) -> None:
    pytest.importorskip("pathspec")

    kept = tmp_path / "kept.py"
    ignored = tmp_path / "ignored.py"
    kept.write_text("TODO kept\n", encoding="utf-8")
    ignored.write_text("TODO ignored\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="python", regex=False)

    assert [result.path for result in results] == [kept]


def test_python_backend_uses_pathspec_gitignore_for_directory_when_available(tmp_path: Path) -> None:
    pytest.importorskip("pathspec")

    kept = tmp_path / "kept.py"
    ignored_dir = tmp_path / "build"
    ignored_file = ignored_dir / "ignored.py"
    ignored_dir.mkdir()
    kept.write_text("TODO kept\n", encoding="utf-8")
    ignored_file.write_text("TODO ignored\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="python", regex=False)

    assert [result.path for result in results] == [kept]


def test_python_backend_resolves_relative_roots_from_workspace_root(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    src_dir = tmp_path / "src"
    other_dir = tmp_path / "other"
    src_dir.mkdir()
    other_dir.mkdir()
    target = src_dir / "app.py"
    target.write_text("TODO workspace\n", encoding="utf-8")
    monkeypatch.chdir(other_dir)

    results = search("TODO", ["src"], backend="python", regex=False, workspace_root=tmp_path)

    assert [result.path for result in results] == [target]


def test_python_backend_uses_workspace_root_gitignore_when_available(tmp_path: Path) -> None:
    pytest.importorskip("pathspec")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    kept = src_dir / "kept.py"
    ignored = src_dir / "ignored.py"
    kept.write_text("TODO kept\n", encoding="utf-8")
    ignored.write_text("TODO ignored\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")

    results = search("TODO", ["src"], backend="python", regex=False, workspace_root=tmp_path)

    assert [result.path for result in results] == [kept]


def test_python_backend_can_disable_ignore_files(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    kept = src_dir / "kept.py"
    ignored = src_dir / "ignored.py"
    kept.write_text("TODO kept\n", encoding="utf-8")
    ignored.write_text("TODO ignored\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")

    results = search(
        "TODO",
        ["src"],
        backend="python",
        regex=False,
        workspace_root=tmp_path,
        respect_ignore=False,
    )

    assert {result.path for result in results} == {kept, ignored}


def test_python_backend_uses_custom_ignore_files_from_workspace_root(tmp_path: Path) -> None:
    pytest.importorskip("pathspec")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    kept = src_dir / "kept.py"
    ignored = src_dir / "ignored.py"
    kept.write_text("TODO kept\n", encoding="utf-8")
    ignored.write_text("TODO ignored\n", encoding="utf-8")
    (tmp_path / ".agentignore").write_text("src/ignored.py\n", encoding="utf-8")

    results = search(
        "TODO",
        ["src"],
        backend="python",
        regex=False,
        workspace_root=tmp_path,
        ignore_files=(".agentignore",),
    )

    assert [result.path for result in results] == [kept]
