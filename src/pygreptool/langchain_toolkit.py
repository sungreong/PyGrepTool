"""Composable read-only LangChain toolkit for safe project navigation."""

from __future__ import annotations

from typing import Sequence

from .core import DEFAULT_IGNORE_FILES, PathInput
from .langchain_tool import (
    create_langchain_find_files_tool,
    create_langchain_read_context_tool,
    create_langchain_search_tool,
)
from .security_policy import CodeAccessPolicy


def create_pygrep_tools(
    *,
    workspace_root: PathInput | None = None,
    virtual_mode: bool = False,
    policy: CodeAccessPolicy | None = None,
    allowed_roots: Sequence[PathInput] | None = None,
    respect_ignore: bool = True,
    ignore_files: Sequence[PathInput] = DEFAULT_IGNORE_FILES,
):
    """Return read-only tools that can be appended to any LangChain toolkit.

    The three tools have distinct roles; agents should choose the minimal one for
    the question instead of following a fixed sequence. No tool can create,
    modify, move, or delete a file.
    """

    return [
        create_langchain_find_files_tool(
            workspace_root=workspace_root,
            virtual_mode=virtual_mode,
            policy=policy,
            allowed_roots=allowed_roots,
            respect_ignore=respect_ignore,
            ignore_files=ignore_files,
        ),
        create_langchain_search_tool(
            workspace_root=workspace_root,
            virtual_mode=virtual_mode,
            policy=policy,
            allowed_roots=allowed_roots,
            respect_ignore=respect_ignore,
            ignore_files=ignore_files,
        ),
        create_langchain_read_context_tool(
            workspace_root=workspace_root,
            virtual_mode=virtual_mode,
            policy=policy,
            allowed_roots=allowed_roots,
        ),
    ]


try:
    from langchain_core.tools import BaseToolkit
except ImportError:  # pragma: no cover - exercised by optional-dependency users.
    BaseToolkit = None  # type: ignore[assignment,misc]


if BaseToolkit is not None:

    class PyGrepToolkit(BaseToolkit):
        """A read-only toolkit that complements LangChain file-management tools."""

        workspace_root: str | None = None
        virtual_mode: bool = False
        policy: CodeAccessPolicy | None = None
        allowed_roots: list[str] | None = None
        respect_ignore: bool = True
        ignore_files: tuple[str, ...] = DEFAULT_IGNORE_FILES

        def get_tools(self):
            """Return ``find_files``, ``search_code``, and ``read_context``."""

            return create_pygrep_tools(
                workspace_root=self.workspace_root,
                virtual_mode=self.virtual_mode,
                policy=self.policy,
                allowed_roots=self.allowed_roots,
                respect_ignore=self.respect_ignore,
                ignore_files=self.ignore_files,
            )

else:

    class PyGrepToolkit:  # pragma: no cover - defensive import-time error path.
        """Placeholder that explains the optional LangChain dependency."""

        def __init__(self, *args, **kwargs):
            raise ImportError("PyGrepToolkit requires langchain-core. Install pygreptool[agent].")
