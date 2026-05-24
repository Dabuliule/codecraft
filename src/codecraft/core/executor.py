from __future__ import annotations

from dataclasses import dataclass

from codecraft.policy.engine import PolicyEngine
from codecraft.schema.tool import ToolCall
from codecraft.tool.base import ToolResult
from codecraft.tool.registry import ToolRegistry
from codecraft.tool.resolver import ResolvedTool, ToolResolver


@dataclass(frozen=True)
class ExecutionResult:
    resolved: ResolvedTool | None
    result: ToolResult


class Executor:
    """
    Tool Executor。

    职责：
    - 执行 policy check
    - 执行确定性 tool
    """

    def __init__(
            self,
            tool_registry: ToolRegistry,
            policy_engine: PolicyEngine | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.resolver = ToolResolver(tool_registry)
        self.policy_engine = policy_engine or PolicyEngine()

    async def execute(
            self,
            request: ToolCall,
    ) -> ExecutionResult:
        try:
            resolved = self.resolver.resolve(
                request,
            )

            policy_decision = self.policy_engine.check(
                resolved,
            )

            if policy_decision.action != "allow":
                return ExecutionResult(
                    resolved=resolved,
                    result=ToolResult(
                        success=False,
                        content="",
                        error=policy_decision.reason,
                        suggestion=policy_decision.suggestion,
                        data={
                            "policy": policy_decision.model_dump(),
                            "tool": request.tool,
                        },
                    ),
                )

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
                resolved=None,
                result=ToolResult(
                    success=False,
                    content="",
                    error=str(e),
                    suggestion=(
                        "Executor 捕获到未处理异常"
                    ),
                ),
            )
