from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from codecraft.tool.base import BaseTool


class ToolProvider(ABC):
    name: str

    @abstractmethod
    def tools(self) -> Iterable[BaseTool]: ...


class AsyncToolProvider(ABC):
    name: str

    @abstractmethod
    async def start(self) -> Iterable[BaseTool]: ...

    @abstractmethod
    async def close(self) -> None: ...
