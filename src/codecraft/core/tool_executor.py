from __future__ import annotations

from dataclasses import dataclass

from codecraft.schema.tool import ToolCall
from codecraft.tool.base import ToolResult
from codecraft.tool.registry import ToolRegistry
from codecraft.tool.resolver import ResolvedTool, ToolResolver


@dataclass(frozen=True)
class ExecutionResult:
    resolved: ResolvedTool | None
    result: ToolResult


class ToolExecutor:
    """
    Tool 执行适配器。

    职责：
    - 解析 ToolCall
    - 执行确定性 tool
    - 归一化执行结果
    """

    def __init__(
            self,
            tool_registry: ToolRegistry,
    ) -> None:
        self.tool_registry = tool_registry
        self.resolver = ToolResolver(tool_registry)

    async def execute(
            self,
            request: ToolCall,
    ) -> ExecutionResult:
        try:
            resolved = self.resolve(request)

            return await self._run_resolved(resolved)

        except Exception as e:
            return self.exception_result(e)

    def resolve(
            self,
            request: ToolCall,
    ) -> ResolvedTool:
        return self.resolver.resolve(
            request,
        )

    @staticmethod
    async def _run_resolved(
            resolved: ResolvedTool,
    ) -> ExecutionResult:
        try:
            raw_result = await resolved.tool.arun(
                resolved.args,
            )

            result = ToolResult.from_value(
                raw_result
            )

            return ExecutionResult(
                resolved=resolved,
                result=result,
            )

        except Exception as e:
            return ExecutionResult(
                resolved=resolved,
                result=ToolResult(
                    success=False,
                    content="",
                    error=str(e),
                    suggestion=(
                        "ToolExecutor 捕获到未处理异常"
                    ),
                ),
            )

    @staticmethod
    def exception_result(
            error: Exception,
            resolved: ResolvedTool | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            resolved=resolved,
            result=ToolResult(
                success=False,
                content="",
                error=str(error),
                suggestion=(
                    "ToolExecutor 捕获到未处理异常"
                ),
            ),
        )
