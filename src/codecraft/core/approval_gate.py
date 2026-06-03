from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from codecraft.core.tool_executor import ExecutionResult, ToolExecutor
from codecraft.policy.approval import ApprovalPolicy
from codecraft.schema.approval import ApprovalDecision, ApprovalRequest
from codecraft.schema.event import (
    ApprovalDecisionEvent,
    ApprovalRequestEvent,
    RuntimeEvent,
    ToolExecutionEvent,
)
from codecraft.schema.tool import ToolCall
from codecraft.tool.base import ToolResult

EventEmitter = Callable[[RuntimeEvent], Awaitable[RuntimeEvent]]


@dataclass(frozen=True)
class ApprovalGateRequest:
    step_id: str
    tool_call: ToolCall


@dataclass(frozen=True)
class ApprovalGateOutcome:
    events: list[RuntimeEvent]
    tool_call: ToolCall
    execution: ExecutionResult


class ApprovalGate:
    def __init__(
            self,
            *,
            approval_policy: ApprovalPolicy,
            tool_executor: ToolExecutor,
    ) -> None:
        self.approval_policy = approval_policy
        self.tool_executor = tool_executor

    def build_request(
            self,
            request: ApprovalGateRequest,
    ) -> ApprovalRequest | None:
        return self.approval_policy.build_request(
            approval_id=f"{request.step_id}-approval",
            tool_call=request.tool_call,
        )

    @staticmethod
    def build_request_event(
            request: ApprovalRequest,
    ) -> ApprovalRequestEvent:
        return ApprovalRequestEvent(
            approval_id=request.approval_id,
            tool=request.tool_call.tool,
            args=request.tool_call.args,
            reason=request.reason,
            suggestion=request.suggestion,
            data=request.data,
        )

    @staticmethod
    def build_decision_event(
            request: ApprovalRequest,
            decision: ApprovalDecision,
    ) -> ApprovalDecisionEvent:
        edited_args = (
            decision.edited_tool_call.args
            if decision.edited_tool_call
            else None
        )

        return ApprovalDecisionEvent(
            approval_id=request.approval_id,
            tool=request.tool_call.tool,
            action=decision.action,
            reason=decision.reason,
            edited_args=edited_args,
        )

    async def apply_decision(
            self,
            *,
            approval_request: ApprovalRequest,
            decision: ApprovalDecision,
            emit: EventEmitter | None = None,
    ) -> ApprovalGateOutcome:
        if decision.action == "reject":
            return ApprovalGateOutcome(
                events=[],
                tool_call=approval_request.tool_call,
                execution=self._rejected_result(
                    tool_call=approval_request.tool_call,
                    reason=decision.reason,
                    approval_id=approval_request.approval_id,
                ),
            )

        if decision.action == "edit":
            tool_call = decision.edited_tool_call
            assert tool_call is not None
        else:
            tool_call = approval_request.tool_call

        return await self.run_tool(
            tool_call=tool_call,
            emit=emit,
        )

    async def run_tool(
            self,
            *,
            tool_call: ToolCall,
            emit: EventEmitter | None = None,
    ) -> ApprovalGateOutcome:
        event = ToolExecutionEvent(
            tool=tool_call.tool,
            tool_input=tool_call.args,
        )
        execution = await self.tool_executor.execute(tool_call)
        events: list[RuntimeEvent] = []
        await self._record_event(
            events=events,
            event=event,
            emit=emit,
        )

        return ApprovalGateOutcome(
            events=events,
            tool_call=tool_call,
            execution=execution,
        )

    @staticmethod
    async def _record_event(
            *,
            events: list[RuntimeEvent],
            event: RuntimeEvent,
            emit: EventEmitter | None,
    ) -> None:
        if emit is None:
            events.append(event)
            return

        events.append(await emit(event))

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
