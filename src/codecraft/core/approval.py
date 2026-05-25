from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from codecraft.schema.approval import ApprovalDecision, ApprovalRequest
from codecraft.schema.event import ApprovalDecisionEvent, ApprovalRequestEvent

ApprovalHandler = Callable[
    [ApprovalRequestEvent],
    ApprovalDecision | Awaitable[ApprovalDecision],
]


class ApprovalBroker:
    """Resolve approval requests through a human-facing channel."""

    def __init__(
            self,
            handler: ApprovalHandler | None = None,
    ) -> None:
        self.handler = handler

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

    async def decide(
            self,
            request_event: ApprovalRequestEvent,
    ) -> ApprovalDecision:
        if self.handler is None:
            return ApprovalDecision.reject("rejected by default")

        decision = self.handler(request_event)
        if inspect.isawaitable(decision):
            decision = await decision

        if not isinstance(decision, ApprovalDecision):
            raise TypeError("Approval handler must return ApprovalDecision.")

        return decision
