from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from codecraft.schema.tool import ToolCall

ApprovalDecisionKind = Literal["approve", "reject", "edit"]


class ApprovalRequest(BaseModel):
    approval_id: str
    tool_call: ToolCall
    reason: str
    suggestion: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: ApprovalDecisionKind
    reason: str | None = None
    edited_tool_call: ToolCall | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "ApprovalDecision":
        if self.decision == "edit" and self.edited_tool_call is None:
            raise ValueError("edit approval requires edited_tool_call")

        if self.decision != "edit" and self.edited_tool_call is not None:
            raise ValueError("edited_tool_call is only valid for edit approval")

        return self

    @classmethod
    def approve(
            cls,
            reason: str | None = None,
    ) -> "ApprovalDecision":
        return cls(
            decision="approve",
            reason=reason,
        )

    @classmethod
    def reject(
            cls,
            reason: str | None = None,
    ) -> "ApprovalDecision":
        return cls(
            decision="reject",
            reason=reason,
        )

    @classmethod
    def edit(
            cls,
            tool_call: ToolCall,
            reason: str | None = None,
    ) -> "ApprovalDecision":
        return cls(
            decision="edit",
            reason=reason,
            edited_tool_call=tool_call,
        )
