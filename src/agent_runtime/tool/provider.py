from __future__ import annotations

from abc import ABC, abstractmethod
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
            ReadFileTool(),
            WriteFileTool(),
            DeleteFileTool(),
            FileExistsTool(),
            ListDirTool(),
            MakeDirTool(),
            FinalAnswerTool(),
            ShellExecTool(),
        )
