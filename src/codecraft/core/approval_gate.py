from __future__ import annotations

from dataclasses import dataclass

from codecraft.core.approval import ApprovalBroker
from codecraft.core.tool_executor import ExecutionResult, ToolExecutor
from codecraft.policy.approval import ApprovalPolicy
from codecraft.schema.event import RuntimeEvent, ToolExecutionEvent
from codecraft.schema.tool import ToolCall
from codecraft.tool.base import ToolResult


@dataclass(frozen=True)
class ApprovalGateRequest:
    step_id: str
    tool_call: ToolCall


@dataclass(frozen=True)
class ApprovalGateOutcome:
    events: list[RuntimeEvent]
    execution: ExecutionResult


class ApprovalGate:
    def __init__(
            self,
            *,
            approval_policy: ApprovalPolicy,
            approval_broker: ApprovalBroker,
            tool_executor: ToolExecutor,
    ) -> None:
        self.approval_policy = approval_policy
        self.approval_broker = approval_broker
        self.tool_executor = tool_executor

    async def run(
            self,
            request: ApprovalGateRequest,
    ) -> ApprovalGateOutcome:
        approval_request = self.approval_policy.build_request(
            approval_id=f"{request.step_id}-approval",
            tool_call=request.tool_call,
        )

        if approval_request is None:
            return await self._run_tool(
                tool_call=request.tool_call,
            )

        events: list[RuntimeEvent] = []
        request_event = self.approval_broker.build_request_event(
            approval_request
        )
        events.append(request_event)

        decision = await self.approval_broker.decide(request_event)
        decision_event = self.approval_broker.build_decision_event(
            approval_request,
            decision,
        )
        events.append(decision_event)

        if decision.action == "reject":
            return ApprovalGateOutcome(
                events=events,
                execution=self._rejected_result(
                    tool_call=request.tool_call,
                    reason=decision.reason,
                    approval_id=approval_request.approval_id,
                ),
            )

        if decision.action == "edit":
            tool_call = decision.edited_tool_call
            assert tool_call is not None
        else:
            tool_call = request.tool_call

        outcome = await self._run_tool(
            tool_call=tool_call,
        )

        return ApprovalGateOutcome(
            events=[
                *events,
                *outcome.events,
            ],
            execution=outcome.execution,
        )

    async def _run_tool(
            self,
            *,
            tool_call: ToolCall,
    ) -> ApprovalGateOutcome:
        return ApprovalGateOutcome(
            events=[
                ToolExecutionEvent(
                    tool=tool_call.tool,
                    tool_input=tool_call.args,
                )
            ],
            execution=await self.tool_executor.execute(tool_call),
        )

    @staticmethod
    def _rejected_result(
            *,
            tool_call: ToolCall,
            reason: str | None,
            approval_id: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            resolved=None,
            result=ToolResult(
                success=False,
                content="",
                error=reason or "用户拒绝执行需要审批的工具",
                data={
                    "tool": tool_call.tool,
                    "approval": {
                        "approval_id": approval_id,
                        "action": "reject",
                    },
                },
            ),
        )
