from __future__ import annotations

from pathlib import Path

from pygreptool import read_context, search


def test_auto_backend_returns_normalized_results(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO auto\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="auto", regex=False)

    assert len(results) == 1
    assert results[0].path == target
    assert results[0].line_number == 1
    assert results[0].column == 1
    assert results[0].backend in {"rg", "grep", "python"}


def test_max_results_limits_output(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO one\nTODO two\nTODO three\n", encoding="utf-8")

    results = search("TODO", target, backend="python", regex=False, max_results=2)

    assert len(results) == 2
    assert [result.line_number for result in results] == [1, 2]


def test_no_match_returns_empty_list(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("nothing here\n", encoding="utf-8")

    assert search("TODO", target, backend="python", regex=False) == []


def test_smart_backend_uses_python_for_single_file(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO smart\n", encoding="utf-8")

    results = search("TODO", target, backend="smart", regex=False)

    assert len(results) == 1
    assert results[0].path == target
    assert results[0].backend == "python"


def test_smart_backend_uses_python_for_small_directory(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO smart directory\n", encoding="utf-8")

    results = search("TODO", tmp_path, backend="smart", regex=False)

    assert len(results) == 1
    assert results[0].path == target
    assert results[0].backend == "python"


def test_search_includes_default_context(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\nTODO hit\nfour\nfive\n", encoding="utf-8")

    results = search("TODO", target, backend="python", regex=False)

    assert len(results) == 1
    assert results[0].context is not None
    assert results[0].context.start_line == 1
    assert results[0].context.end_line == 5
    assert [line.line_number for line in results[0].context.lines] == [1, 2, 3, 4, 5]
    assert [line.is_match for line in results[0].context.lines] == [False, False, True, False, False]


def test_search_can_disable_context(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\nTODO hit\nthree\n", encoding="utf-8")

    results = search("TODO", target, backend="python", regex=False, context_before=0, context_after=0)

    assert len(results) == 1
    assert results[0].context is None


def test_search_context_clamps_at_file_edges(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("TODO first\nsecond\n", encoding="utf-8")

    results = search("TODO", target, backend="python", regex=False, context_before=3, context_after=3)

    assert results[0].context is not None
    assert results[0].context.start_line == 1
    assert results[0].context.end_line == 2


def test_multiple_search_matches_each_get_context(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\nTODO first\nthree\nTODO second\nfive\n", encoding="utf-8")

    results = search("TODO", target, backend="python", regex=False, context_before=1, context_after=1)

    assert len(results) == 2
    assert all(result.context is not None for result in results)
    assert [result.context.start_line for result in results if result.context is not None] == [1, 3]
    assert [result.context.end_line for result in results if result.context is not None] == [3, 5]


def test_read_context_reads_around_line(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    context = read_context(target, line_number=3, before=1, after=1)

    assert context.start_line == 2
    assert context.end_line == 4
    assert context.content == "two\nthree\nfour"
    assert [line.line for line in context.lines] == ["two", "three", "four"]
    assert [line.is_match for line in context.lines] == [False, True, False]


def test_read_context_full_mode_respects_limits(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    context = read_context(target, full=True, max_lines=2)

    assert context.start_line == 1
    assert context.end_line == 2
    assert context.content == "one\ntwo"
    assert [line.line for line in context.lines] == ["one", "two"]
    assert context.truncated is True


def test_read_context_respects_max_chars(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("abcdef\nsecond\n", encoding="utf-8")

    context = read_context(target, full=True, max_chars=3)

    assert context.content == "abc"
    assert context.truncated is True
