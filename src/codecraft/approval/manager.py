from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from codecraft.approval.policy import ApprovalPolicy
from codecraft.core.ids import new_id
from codecraft.core.turn_context import TurnContext
from codecraft.sandbox.command_policy import CommandPolicy, CommandRisk
from codecraft.schema.tool import ToolCall, ToolEffect
from codecraft.tool.base import BaseTool


class ApprovalEvaluation(BaseModel):
    requires_approval: bool
    reason: str
    risk: str


class ApprovalRequest(BaseModel):
    approval_id: str
    session_id: str
    turn_id: str
    call_id: str
    tool_name: str
    arguments: dict
    reason: str
    risk: str


class ApprovalDecision(BaseModel):
    approval_id: str
    approved: bool
    reviewer: Literal["user", "auto"] = "auto"
    reason: str | None = None

    @classmethod
    def approve(cls, approval_id: str, reason: str | None = None) -> ApprovalDecision:
        return cls(approval_id=approval_id, approved=True, reason=reason)

    @classmethod
    def deny(cls, approval_id: str, reason: str | None = None) -> ApprovalDecision:
        return cls(approval_id=approval_id, approved=False, reason=reason)


class ApprovalReviewer(ABC):
    @abstractmethod
    async def review(self, request: ApprovalRequest) -> ApprovalDecision:
        ...


class AutoApprovalReviewer(ApprovalReviewer):
    def __init__(self, *, approved: bool = True, reason: str | None = None) -> None:
        self.approved = approved
        self.reason = reason
        self.requests: list[ApprovalRequest] = []

    async def review(self, request: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(request)
        if self.approved:
            return ApprovalDecision.approve(request.approval_id, self.reason)
        return ApprovalDecision.deny(request.approval_id, self.reason)


class ApprovalManager:
    def __init__(
        self,
        *,
        policy: ApprovalPolicy = ApprovalPolicy.NEVER,
        reviewer: ApprovalReviewer | None = None,
        command_policy: CommandPolicy | None = None,
    ) -> None:
        self.policy = policy
        self.reviewer = reviewer or AutoApprovalReviewer()
        self.command_policy = command_policy or CommandPolicy()

    async def evaluate(
        self,
        tool: BaseTool,
        call: ToolCall,
        args: BaseModel,
        context: TurnContext,
    ) -> ApprovalEvaluation:
        if self.policy == ApprovalPolicy.NEVER:
            return ApprovalEvaluation(
                requires_approval=False,
                reason="approval disabled by policy",
                risk="safe",
            )

        if call.name == "bash":
            command = str(call.arguments.get("command", ""))
            decision = self.command_policy.classify(
                command,
                network_access=context.network_access,
            )
            if decision.risk == CommandRisk.DENY:
                return ApprovalEvaluation(
                    requires_approval=False,
                    reason=decision.reason,
                    risk=decision.risk,
                )
            return ApprovalEvaluation(
                requires_approval=decision.requires_approval,
                reason=decision.reason,
                risk=decision.risk,
            )

        if self.policy == ApprovalPolicy.UNTRUSTED:
            write_effects = {ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXEC, ToolEffect.NETWORK, ToolEffect.EXTERNAL}
            if tool.effects & write_effects:
                return ApprovalEvaluation(
                    requires_approval=True,
                    reason=f"{tool.name} has side effects",
                    risk="prompt",
                )

        if self.policy == ApprovalPolicy.ON_REQUEST and tool.requires_approval:
            return ApprovalEvaluation(
                requires_approval=True,
                reason=f"{tool.name} requires approval",
                risk="prompt",
            )

        return ApprovalEvaluation(
            requires_approval=False,
            reason="tool is allowed",
            risk="safe",
        )

    async def request(self, request: ApprovalRequest) -> ApprovalDecision:
        return await self.reviewer.review(request)

    @staticmethod
    def build_request(
        *,
        call: ToolCall,
        context: TurnContext,
        evaluation: ApprovalEvaluation,
    ) -> ApprovalRequest:
        return ApprovalRequest(
            approval_id=new_id("appr_"),
            session_id=context.session_id,
            turn_id=context.turn_id,
            call_id=call.call_id,
            tool_name=call.name,
            arguments=call.arguments,
            reason=evaluation.reason,
            risk=evaluation.risk,
        )
