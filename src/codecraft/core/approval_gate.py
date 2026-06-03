from __future__ import annotations

from dataclasses import dataclass

from codecraft.core.tool_executor import ExecutionResult, ToolExecutor
from codecraft.policy.approval import ApprovalPolicy
from codecraft.schema.approval import ApprovalDecision, ApprovalRequest
from codecraft.schema.event import (
    ApprovalDecisionEvent,
    ApprovalRequestEvent,
)
from codecraft.schema.tool import ToolCall
from codecraft.tool.base import ToolResult


@dataclass(frozen=True)
class ApprovalGateRequest:
    step_id: str
    tool_call: ToolCall


@dataclass(frozen=True)
class ApprovalGateOutcome:
    tool_call: ToolCall
    execution: ExecutionResult
    tool_executed: bool


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
    ) -> ApprovalGateOutcome:
        if decision.action == "reject":
            return ApprovalGateOutcome(
                tool_call=approval_request.tool_call,
                execution=self._rejected_result(
                    tool_call=approval_request.tool_call,
                    reason=decision.reason,
                    approval_id=approval_request.approval_id,
                ),
                tool_executed=False,
            )

        if decision.action == "edit":
            tool_call = decision.edited_tool_call
            assert tool_call is not None
        else:
            tool_call = approval_request.tool_call

        return await self.run_tool(
            tool_call=tool_call,
        )

    async def run_tool(
            self,
            *,
            tool_call: ToolCall,
    ) -> ApprovalGateOutcome:
        return ApprovalGateOutcome(
            tool_call=tool_call,
            execution=await self.tool_executor.execute(tool_call),
            tool_executed=True,
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
