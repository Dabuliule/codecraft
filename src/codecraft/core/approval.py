from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from codecraft.schema.event import ApprovalDecisionEvent, ApprovalRequestEvent
from codecraft.schema.policy import PolicyDecision
from codecraft.tool.resolver import ResolvedTool

ApprovalHandler = Callable[[ApprovalRequestEvent], bool | Awaitable[bool]]


@dataclass(frozen=True)
class ApprovalOutcome:
    request: ApprovalRequestEvent
    decision: ApprovalDecisionEvent

    @property
    def approved(self) -> bool:
        return self.decision.approved


class ApprovalFlow:
    """Build and resolve approval events for policy-gated tool execution."""

    def __init__(
            self,
            handler: ApprovalHandler | None = None,
    ) -> None:
        self.handler = handler

    async def request(
            self,
            *,
            approval_id: str,
            resolved: ResolvedTool,
            policy_decision: PolicyDecision,
    ) -> ApprovalOutcome:
        request_event = ApprovalRequestEvent(
            **self.build_request_data(
                approval_id=approval_id,
                resolved=resolved,
                policy_decision=policy_decision,
            )
        )

        decision_event = await self.decide(request_event)

        return ApprovalOutcome(
            request=request_event,
            decision=decision_event,
        )

    def build_request(
            self,
            *,
            approval_id: str,
            resolved: ResolvedTool,
            policy_decision: PolicyDecision,
    ) -> ApprovalRequestEvent:
        return ApprovalRequestEvent(
            **self.build_request_data(
                approval_id=approval_id,
                resolved=resolved,
                policy_decision=policy_decision,
            )
        )

    @staticmethod
    def build_request_data(
            *,
            approval_id: str,
            resolved: ResolvedTool,
            policy_decision: PolicyDecision,
    ) -> dict:
        return {
            "approval_id": approval_id,
            "tool": resolved.tool_call.tool,
            "args": resolved.args,
            "reason": policy_decision.reason,
            "suggestion": policy_decision.suggestion,
            "data": policy_decision.data,
        }

    async def decide(
            self,
            request_event: ApprovalRequestEvent,
    ) -> ApprovalDecisionEvent:
        approved = await self._resolve(request_event)

        return ApprovalDecisionEvent(
            approval_id=request_event.approval_id,
            tool=request_event.tool,
            approved=approved,
            reason=(
                "approved by user"
                if approved
                else "rejected by user"
            ),
        )

    async def _resolve(
            self,
            request_event: ApprovalRequestEvent,
    ) -> bool:
        if self.handler is None:
            return False

        decision = self.handler(request_event)
        if inspect.isawaitable(decision):
            decision = await decision

        if not isinstance(decision, bool):
            raise TypeError("Approval handler must return bool.")

        return decision
