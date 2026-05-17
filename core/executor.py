from schema import ToolAction
from schema.step import Step
from tool import ToolResult
from tool.registry import ToolRegistry


class Executor:
    """Single-step executor for tool-using agents."""

    def __init__(
            self,
            tool_registry: ToolRegistry,
    ) -> None:
        self.tool_registry = tool_registry

    async def execute(self, action: ToolAction) -> Step:
        try:
            result = await self.tool_registry.arun(
                action.tool,
                action.tool_input or {},
            )
            result = ToolResult.from_value(result)

        except Exception as e:
            result = ToolResult(
                success=False,
                content="",
                error=str(e),
                suggestion="Executor 捕获到未处理异常。",
            )

        return Step(
            action=action,
            observation=result,
            metadata={
                "success": result.success,
                "error": result.error,
                "suggestion": result.suggestion
            },
        )
