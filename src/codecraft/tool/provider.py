from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from codecraft.tool.base import BaseTool


class ToolProvider(ABC):
    name: str

    @abstractmethod
    def tools(self) -> Iterable[BaseTool]: ...
