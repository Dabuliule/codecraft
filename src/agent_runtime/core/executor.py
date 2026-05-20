from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.operation.base import OperationResult
from agent_runtime.operation.registry import OperationRegistry
from agent_runtime.operation.resolver import OperationResolver, ResolvedOperation
from agent_runtime.policy.engine import PolicyEngine
from agent_runtime.schema.intent import IntentRequest


@dataclass(frozen=True)
class ExecutionResult:
    resolved: ResolvedOperation | None
    result: OperationResult


class Executor:
    """
    Operation Executor。

    职责：
    - 将 intent 解析为 operation
    - 执行 policy check
    - 执行确定性 operation
    """

    def __init__(
            self,
            operation_registry: OperationRegistry,
            policy_engine: PolicyEngine | None = None,
    ) -> None:
        self.operation_registry = operation_registry
        self.resolver = OperationResolver(operation_registry)
        self.policy_engine = policy_engine or PolicyEngine()

    async def execute(
            self,
            request: IntentRequest,
    ) -> ExecutionResult:
        try:
            resolved = self.resolver.resolve(
                request,
            )

            policy_decision = self.policy_engine.check(
                resolved,
            )

            if not policy_decision.allowed:
                return ExecutionResult(
                    resolved=resolved,
                    result=OperationResult(
                        success=False,
                        content="",
                        error=policy_decision.reason,
                        suggestion=policy_decision.suggestion,
                        data={
                            "policy": policy_decision.model_dump(),
                            "operation": resolved.operation.name,
                            "intent": request.intent,
                        },
                    ),
                )

            raw_result = await resolved.operation.arun(
                resolved.args,
            )

            result = OperationResult.from_value(
                raw_result
            )

            return ExecutionResult(
                resolved=resolved,
                result=result,
            )

        except Exception as e:
            return ExecutionResult(
                resolved=None,
                result=OperationResult(
                    success=False,
                    content="",
                    error=str(e),
                    suggestion=(
                        "Executor 捕获到未处理异常"
                    ),
                ),
            )
