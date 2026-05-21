from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from agent_runtime.tool.base import BaseTool


class ToolRegistry:
    """Tool 注册中心。"""

    def __init__(
            self,
            tools: Iterable[BaseTool] | None = None,
            *,
            include_builtins: bool = True,
    ) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._tags: Dict[str, set[str]] = {}

        if include_builtins:
            self.register_builtin_tools()

        for tool in tools or []:
            self.register(tool)

    def register(
            self,
            tool: BaseTool,
            *,
            overwrite: bool = False,
    ) -> None:
        name = getattr(tool, "name", "")
        if not name:
            raise ValueError("Tool 必须定义非空 name。")
        if not overwrite and name in self._tools:
            raise ValueError(f"Tool '{name}' 已被注册。")

        if overwrite and name in self._tools:
            for names in self._tags.values():
                names.discard(name)

        self._tools[name] = tool
        for tag in getattr(tool, "tags", set()) or set():
            self._tags.setdefault(tag, set()).add(name)

    def inject(
            self,
            tools: Iterable[BaseTool],
            *,
            overwrite: bool = False,
    ) -> None:
        for tool in tools:
            self.register(tool, overwrite=overwrite)

    def register_builtin_tools(self) -> None:
        from agent_runtime.tool import builtin as builtin_module

        for class_name in getattr(builtin_module, "__all__", []):
            tool_cls = getattr(builtin_module, class_name, None)
            if not isinstance(tool_cls, type):
                continue
            if not issubclass(tool_cls, BaseTool):
                continue
            self.register(tool_cls())

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self, tag: str | None = None) -> List[BaseTool]:
        if tag is None:
            return list(self._tools.values())
        return [
            self._tools[name]
            for name in sorted(self._tags.get(tag, set()))
        ]

    def names(self, tag: str | None = None) -> List[str]:
        if tag is None:
            return list(self._tools.keys())
        return sorted(self._tags.get(tag, set()))

    def tags(self) -> List[str]:
        return sorted(self._tags.keys())

    def tool_schemas(self) -> List[dict]:
        return [
            tool.tool_schema()
            for tool in self._tools.values()
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
