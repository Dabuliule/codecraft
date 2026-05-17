from __future__ import annotations

from typing import Any, Dict, List, Optional

from observability.decorators import traced
from observability.trace import TraceLogger
from .base import BaseTool, ToolResult


class ToolRegistry:
    """工具注册中心。"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self.register_builtin_tools()

    def register(self, tool: BaseTool, *, overwrite: bool = False) -> None:
        """注册一个工具实例。"""
        name = getattr(tool, "name", "")
        if not name:
            raise ValueError("工具必须定义非空 name。")
        if not overwrite and name in self._tools:
            raise ValueError(f"工具 '{name}' 已被注册。")
        self._tools[name] = tool

    def register_builtin_tools(self) -> None:
        """自动注册 tool.builtin 下导出的工具类。"""
        from . import builtin as builtin_module

        for name in getattr(builtin_module, "__all__", []):
            tool_cls = getattr(builtin_module, name, None)
            if not isinstance(tool_cls, type):
                continue
            if not issubclass(tool_cls, BaseTool):
                continue
            self.register(tool_cls())

    def get(self, name: str) -> Optional[BaseTool]:
        """通过名称获取工具实例。"""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """返回所有已注册工具。"""
        return list(self._tools.values())

    def names(self) -> List[str]:
        """返回所有已注册工具名称。"""
        return list(self._tools.keys())

    def tool_schemas(self) -> List[Dict[str, Any]]:
        """导出 function-calling 所需的 schema 列表。"""
        return [tool.tool_schema() for tool in self._tools.values()]

    @traced(component="tool", name="tool.run")
    def run(self, name: str, params: Dict[str, Any]) -> ToolResult:
        """按工具名执行工具。"""
        tool = self.get(name)
        if tool is None:
            TraceLogger.log("tool.run.missing", {"tool": name}, level="WARN")
            return ToolResult(
                success=False,
                content="",
                error=f"未找到工具: {name}",
                suggestion="请检查工具名称是否正确。",
            )
        result = tool.run(params)
        return result

    @traced(component="tool", name="tool.arun")
    async def arun(self, name: str, params: Dict[str, Any]) -> ToolResult:
        """按工具名异步执行工具。"""
        tool = self.get(name)
        if tool is None:
            TraceLogger.log("tool.arun.missing", {"tool": name}, level="WARN")
            return ToolResult(
                success=False,
                content="",
                error=f"未找到工具: {name}",
                suggestion="请检查工具名称是否正确。",
            )
        result = await tool.arun(params)
        return result

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
