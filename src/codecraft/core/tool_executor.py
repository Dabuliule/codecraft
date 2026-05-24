from __future__ import annotations

from dataclasses import dataclass

from codecraft.policy.engine import PolicyEngine
from codecraft.schema.policy import PolicyDecision
from codecraft.schema.tool import ToolCall
from codecraft.tool.base import ToolResult
from codecraft.tool.registry import ToolRegistry
from codecraft.tool.resolver import ResolvedTool, ToolResolver


@dataclass(frozen=True)
class ExecutionResult:
    resolved: ResolvedTool | None
    result: ToolResult


@dataclass(frozen=True)
class PreparedExecution:
    resolved: ResolvedTool
    policy_decision: PolicyDecision


class ToolExecutor:
    """
    Tool 执行适配器。

    职责：
    - 解析 ToolCall
    - 执行 policy check
    - 执行确定性 tool
    - 归一化执行结果
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
            resolved = self.resolve(request)

            policy_decision = self.check_policy(resolved)

            if policy_decision.action != "allow":
                return self.policy_failure_result(
                    resolved=resolved,
                    policy_decision=policy_decision,
                )

            return await self.execute_prepared(
                PreparedExecution(
                    resolved=resolved,
                    policy_decision=policy_decision,
                )
            )

        except Exception as e:
            return ExecutionResult(
                resolved=None,
                result=ToolResult(
                    success=False,
                    content="",
                    error=str(e),
                    suggestion=(
                        "ToolExecutor 捕获到未处理异常"
                    ),
                ),
            )

    def prepare(
            self,
            request: ToolCall,
    ) -> PreparedExecution:
        resolved = self.resolve(request)
        policy_decision = self.check_policy(resolved)

        return PreparedExecution(
            resolved=resolved,
            policy_decision=policy_decision,
        )

    async def execute_allowed(
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

    def check_policy(
            self,
            resolved: ResolvedTool,
    ) -> PolicyDecision:
        return self.policy_engine.check(
            resolved,
        )

    async def execute_prepared(
            self,
            prepared: PreparedExecution,
    ) -> ExecutionResult:
        return await self._run_resolved(
            prepared.resolved,
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
    def policy_failure_result(
            resolved: ResolvedTool,
            policy_decision: PolicyDecision,
    ) -> ExecutionResult:
        return ExecutionResult(
            resolved=resolved,
            result=ToolResult(
                success=False,
                content="",
                error=policy_decision.reason,
                suggestion=policy_decision.suggestion,
                data={
                    "policy": policy_decision.model_dump(),
                    "tool": resolved.tool_call.tool,
                },
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
