from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from codecraft.schema.result import AgentResult


class RuntimeEvent(BaseModel):
    type: str
    trace_id: str | None = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class ThoughtEvent(RuntimeEvent):
    type: Literal["thought"] = "thought"

    thought: str


class ToolCallEvent(RuntimeEvent):
    type: Literal["tool_call"] = "tool_call"

    tool: str
    args: dict


class ToolExecutionEvent(RuntimeEvent):
    type: Literal["tool_execution"] = "tool_execution"
    tool: str

    tool_input: dict = Field(default_factory=dict)


class ApprovalRequestEvent(RuntimeEvent):
    type: Literal["approval_request"] = "approval_request"

    approval_id: str
    tool: str
    args: dict
    reason: str
    suggestion: str | None = None
    data: Any = None


class ApprovalDecisionEvent(RuntimeEvent):
    type: Literal["approval_decision"] = "approval_decision"

    approval_id: str
    tool: str
    approved: bool
    reason: str | None = None


class ObservationEvent(RuntimeEvent):
    type: Literal["observation"] = "observation"

    content: str

    success: bool

    data: Any = None

    error: str | None = None

    suggestion: str | None = None


class WarningEvent(RuntimeEvent):
    type: Literal["warning"] = "warning"

    message: str


class FinalResultEvent(RuntimeEvent):
    type: Literal["final_result"] = "final_result"

    result: AgentResult
