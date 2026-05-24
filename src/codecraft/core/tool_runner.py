from __future__ import annotations

from dataclasses import dataclass

from codecraft.core.approval import ApprovalFlow
from codecraft.core.tool_executor import ExecutionResult, PreparedExecution, ToolExecutor
from codecraft.schema.event import RuntimeEvent, ToolExecutionEvent
from codecraft.schema.tool import ToolCall


@dataclass(frozen=True)
class ToolRunRequest:
    step_id: str
    tool_call: ToolCall


@dataclass(frozen=True)
class ToolRunOutcome:
    events: list[RuntimeEvent]
    execution: ExecutionResult


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
    ) -> ToolRunOutcome:
        events: list[RuntimeEvent] = []

        try:
            prepared = self.executor.prepare(request.tool_call)
            policy_decision = prepared.policy_decision

            if policy_decision.action == "deny":
                return ToolRunOutcome(
                    events=events,
                    execution=self.executor.policy_failure_result(
                        resolved=prepared.resolved,
                        policy_decision=policy_decision,
                    )
                )

            if policy_decision.action == "require_approval":
                request_event = self.approval_flow.build_request(
                    approval_id=f"{request.step_id}-approval",
                    resolved=prepared.resolved,
                    policy_decision=policy_decision,
                )

                events.append(request_event)

                decision_event = await self.approval_flow.decide(
                    request_event
                )

                events.append(decision_event)

                if not decision_event.approved:
                    return ToolRunOutcome(
                        events=events,
                        execution=self.executor.approval_rejected_result(
                            resolved=prepared.resolved,
                            policy_decision=policy_decision,
                        )
                    )

            return await self._run_prepared(
                prepared=prepared,
                events=events,
            )

        except Exception as e:
            return ToolRunOutcome(
                events=events,
                execution=self.executor.exception_result(e),
            )

    async def _run_prepared(
            self,
            prepared: PreparedExecution,
            events: list[RuntimeEvent],
    ) -> ToolRunOutcome:
        events.append(
            ToolExecutionEvent(
                tool=prepared.resolved.tool_call.tool,
                tool_input=prepared.resolved.args,
            )
        )

        return ToolRunOutcome(
            events=events,
            execution=await self.executor.execute_prepared(prepared),
        )
