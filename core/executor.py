from __future__ import annotations

from schema.action import ToolAction
from tool import ToolResult
from tool.registry import ToolRegistry


class Executor:
    """
    Tool Executor。

    职责：
    - 执行单个 tool action
    - 捕获工具异常
    - 标准化 ToolResult
    """

    def __init__(
            self,
            tool_registry: ToolRegistry,
    ) -> None:
        self.tool_registry = tool_registry

    async def execute(
            self,
            action: ToolAction,
    ) -> ToolResult:
        try:
            raw_result = await self.tool_registry.arun(
                action.tool,
                action.tool_input or {},
            )

            result = ToolResult.from_value(
                raw_result
            )

        except Exception as e:
            result = ToolResult(
                success=False,
                content="",
                error=str(e),
                suggestion=(
                    "Executor 捕获到未处理异常"
                ),
            )

        return result
