from __future__ import annotations

from collections.abc import Iterable

from codecraft.core.errors import ToolNotFoundError
from codecraft.schema.tool import ToolSpec
from codecraft.tool.base import BaseTool
from codecraft.tool.provider import ToolProvider


class ToolRegistry:
    """按 tool name 管理所有可调用 tool。"""

    def __init__(self, tools: Iterable[BaseTool] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        """注册单个 tool，并拒绝空名称或重复名称。"""
        name = tool.name.strip()
        if not name:
            raise ValueError("tool name must not be empty")

        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")

        self._tools[name] = tool

    def register_provider(self, provider: ToolProvider) -> None:
        """注册一个 provider 暴露出的全部 tool。"""
        for tool in provider.tools():
            self.register(tool)

    def get(self, name: str) -> BaseTool:
        """按名称取 tool，不存在时抛出带 code 的业务异常。"""
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(
                f"tool not found: {name}",
                code="tool_not_found",
                metadata={"tool": name},
            ) from exc

    def list(self) -> list[BaseTool]:
        return list(self._tools.values())

    def specs(self) -> list[ToolSpec]:
        """返回所有 tool 的模型可见描述。"""
        return [tool.spec() for tool in self.list()]
