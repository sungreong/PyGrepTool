from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("langchain_core")

from pygreptool.langchain_toolkit import PyGrepToolkit, create_pygrep_tools


def test_pygrep_toolkit_is_read_only_and_composable(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    tools = PyGrepToolkit(workspace_root=str(tmp_path), allowed_roots=["src"]).get_tools()

    assert [tool.name for tool in tools] == ["find_files", "search_code", "read_context"]
    assert all("write" not in tool.name and "delete" not in tool.name for tool in tools)

    direct_tools = create_pygrep_tools(workspace_root=tmp_path, allowed_roots=["src"])
    assert [tool.name for tool in direct_tools] == ["find_files", "search_code", "read_context"]


def test_pygrep_toolkit_can_extend_langchain_read_only_file_tools(tmp_path: Path) -> None:
    pytest.importorskip("langchain_community")
    from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit

    src = tmp_path / "src"
    src.mkdir()
    langchain_tools = FileManagementToolkit(
        root_dir=str(src),
        selected_tools=["file_search", "list_directory"],
    ).get_tools()
    tools = [*langchain_tools, *PyGrepToolkit(workspace_root=str(tmp_path), allowed_roots=["src"]).get_tools()]

    assert [tool.name for tool in tools] == ["file_search", "list_directory", "find_files", "search_code", "read_context"]
    assert not {"write_file", "file_delete", "move_file", "copy_file"}.intersection(tool.name for tool in tools)


def test_pygrep_toolkit_virtual_mode_returns_virtual_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "service.py").write_text("content\n", encoding="utf-8")
    find_tool = PyGrepToolkit(
        workspace_root=str(tmp_path),
        allowed_roots=["src"],
        virtual_mode=True,
    ).get_tools()[0]

    result = find_tool.invoke({"folder": "/src", "extensions": ["py"]})

    assert '"path": "/src/service.py"' in result
    assert str(tmp_path) not in result
