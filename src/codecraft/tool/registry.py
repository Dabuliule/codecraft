from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from codecraft.tool.base import BaseTool
from codecraft.tool.provider import ToolProvider


class ToolRegistry:
    """Tool 注册中心。

    Registry 只负责：
    - 注册 Provider 暴露出来的 Tool
    - 维护 name -> Tool 索引
    - 维护 tag -> Tool name 索引
    - 提供查询能力
    - 汇总 Tool Schema
    """

    def __init__(
            self,
            providers: Iterable[ToolProvider] | None = None,
    ) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._tags: dict[str, set[str]] = {}

        for provider in providers or ():
            self.register_provider(provider)

    def register_provider(
            self,
            provider: ToolProvider,
    ) -> None:
        """注册一个 ToolProvider 暴露出来的所有 Tool。"""
        if not isinstance(provider, ToolProvider):
            raise TypeError("provider 必须是 ToolProvider 的实例。")

        for tool in provider.tools():
            self._register_tool(tool)

    def _register_tool(
            self,
            tool: BaseTool,
    ) -> None:
        """注册单个 Tool。"""
        if not isinstance(tool, BaseTool):
            raise TypeError("tool 必须是 BaseTool 的实例。")

        name = self._normalize_name(getattr(tool, "name", ""))

        if name in self._tools:
            raise ValueError(f"Tool '{name}' 已被注册。")

        self._tools[name] = tool
        self._add_to_tag_index(name, tool)

    def require(
            self,
            name: str,
    ) -> BaseTool:
        """根据名称查找 Tool。找不到时抛出 KeyError。"""
        normalized_name = self._normalize_name(name)
        tool = self._tools.get(normalized_name)

        if tool is None:
            raise KeyError(f"Tool '{normalized_name}' 未注册。")

        return tool

    def list_tools(
            self,
            tag: str | None = None,
    ) -> list[BaseTool]:
        """列出 Tool。

        如果传入 tag，则只返回该 tag 下的 Tool。
        """
        if tag is None:
            return list(self._tools.values())

        normalized_tag = self._normalize_tag(tag)

        return [
            self._tools[name]
            for name in sorted(self._tags.get(normalized_tag, set()))
            if name in self._tools
        ]

    def names(
            self,
            tag: str | None = None,
    ) -> list[str]:
        """列出 Tool 名称。

        如果传入 tag，则只返回该 tag 下的 Tool 名称。
        """
        if tag is None:
            return list(self._tools.keys())

        normalized_tag = self._normalize_tag(tag)
        return sorted(self._tags.get(normalized_tag, set()))

    def tags(self) -> list[str]:
        """列出当前所有 tag。"""
        return sorted(self._tags.keys())

    def tool_schemas(
            self,
            tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """返回 Tool Schema。

        如果传入 tag，则只返回该 tag 下的 Tool Schema。
        """
        return [
            tool.tool_schema()
            for tool in self.list_tools(tag=tag)
        ]

    def _add_to_tag_index(
            self,
            name: str,
            tool: BaseTool,
    ) -> None:
        """把 Tool 加入 tag 索引。"""
        for tag in self._tool_tags(tool):
            self._tags.setdefault(tag, set()).add(name)

    def _tool_tags(
            self,
            tool: BaseTool,
    ) -> tuple[str, ...]:
        """获取并规范化 Tool tags。"""
        raw_tags = getattr(tool, "tags", ()) or ()

        normalized_tags: set[str] = set()

        for tag in raw_tags:
            normalized_tag = self._normalize_tag(tag)
            if normalized_tag:
                normalized_tags.add(normalized_tag)

        return tuple(sorted(normalized_tags))

    @staticmethod
    def _normalize_name(
            name: str,
    ) -> str:
        """规范化 Tool 名称。"""
        normalized = str(name).strip()

        if not normalized:
            raise ValueError("Tool 名称不能为空。")

        return normalized

    @staticmethod
    def _normalize_tag(
            tag: str,
    ) -> str:
        """规范化 tag。"""
        return str(tag).strip()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(
            self,
            name: str,
    ) -> bool:
        try:
            normalized_name = self._normalize_name(name)
        except ValueError:
            return False

        return normalized_name in self._tools

    def __iter__(self):
        return iter(self._tools.values())
