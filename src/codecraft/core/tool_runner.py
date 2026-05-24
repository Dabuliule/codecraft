from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TypeAlias

from codecraft.core.approval import ApprovalFlow
from codecraft.core.tool_executor import ExecutionResult, PreparedExecution, ToolExecutor
from codecraft.schema.event import RuntimeEvent, ToolExecutionEvent
from codecraft.schema.tool import ToolCall


@dataclass(frozen=True)
class ToolRunRequest:
    step_id: str
    tool_call: ToolCall


@dataclass(frozen=True)
class ToolRunResult:
    execution: ExecutionResult


ToolRunItem: TypeAlias = RuntimeEvent | ToolRunResult


class ToolCallRunner:
    def __init__(
            self,
            executor: ToolExecutor,
            approval_flow: ApprovalFlow,
    ) -> None:
        self.executor = executor
        self.approval_flow = approval_flow

    async def run(
            self,
            request: ToolRunRequest,
    ) -> AsyncIterator[ToolRunItem]:
        try:
            prepared = self.executor.prepare(request.tool_call)
            policy_decision = prepared.policy_decision

            if policy_decision.action == "deny":
                yield ToolRunResult(
                    execution=self.executor.policy_failure_result(
                        resolved=prepared.resolved,
                        policy_decision=policy_decision,
                    )
                )
                return

            if policy_decision.action == "require_approval":
                request_event = self.approval_flow.build_request(
                    approval_id=f"{request.step_id}-approval",
                    resolved=prepared.resolved,
                    policy_decision=policy_decision,
                )

                yield request_event

                decision_event = await self.approval_flow.decide(
                    request_event
                )

                yield decision_event

                if not decision_event.approved:
                    yield ToolRunResult(
                        execution=self.executor.approval_rejected_result(
                            resolved=prepared.resolved,
                            policy_decision=policy_decision,
                        )
                    )
                    return

            async for item in self._run_prepared(prepared):
                yield item

        except Exception as e:
            yield ToolRunResult(
                execution=self.executor.exception_result(e),
            )

    async def _run_prepared(
            self,
            prepared: PreparedExecution,
    ) -> AsyncIterator[ToolRunItem]:
        yield ToolExecutionEvent(
            tool=prepared.resolved.tool_call.tool,
            tool_input=prepared.resolved.args,
        )

        yield ToolRunResult(
            execution=await self.executor.execute_prepared(prepared),
        )
