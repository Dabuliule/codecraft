from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from agent_runtime.tool.base import BaseTool
from agent_runtime.tool.registry import ToolRegistry
from agent_runtime.schema.tool import ToolCall


@dataclass(frozen=True)
class ResolvedTool:
    tool_call: ToolCall
    tool: BaseTool
    args: Dict[str, Any]


class ToolResolver:
    """将 ToolCall 解析为确定性 Tool。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def resolve(self, request: ToolCall) -> ResolvedTool:
        tool = self.registry.get(request.tool)
        if tool is None:
            raise ValueError(f"未找到可处理的 Tool: {request.tool}")

        return ResolvedTool(
            tool_call=request,
            tool=tool,
            args=tool.build_args(request),
        )
