from __future__ import annotations

from abc import ABC, abstractmethod
from os import PathLike
from typing import Iterable

from agent_runtime.tool.base import BaseTool


class ToolProvider(ABC):
    """Tool provider base class."""

    name: str

    @abstractmethod
    def tools(self) -> Iterable[BaseTool]:
        """Return tool instances provided by this provider."""
        raise NotImplementedError


class BuiltinToolProvider(ToolProvider):
    """Provider for built-in runtime tools."""

    name = "builtin"

    def __init__(
            self,
            workspace_root: str | PathLike[str] | None = None,
    ) -> None:
        self.workspace_root = workspace_root

    def tools(self) -> Iterable[BaseTool]:
        from agent_runtime.tool.builtin import (
            DeleteFileTool,
            FileExistsTool,
            FinalAnswerTool,
            ListDirTool,
            MakeDirTool,
            ReadFileTool,
            ShellExecTool,
            WriteFileTool,
        )

        return (
            ReadFileTool(workspace_root=self.workspace_root),
            WriteFileTool(workspace_root=self.workspace_root),
            DeleteFileTool(workspace_root=self.workspace_root),
            FileExistsTool(workspace_root=self.workspace_root),
            ListDirTool(workspace_root=self.workspace_root),
            MakeDirTool(workspace_root=self.workspace_root),
            FinalAnswerTool(),
            ShellExecTool(),
        )
