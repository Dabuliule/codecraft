from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from agent_runtime.schema.result import AgentResult


class RuntimeEvent(BaseModel):
    type: str

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class ThoughtEvent(RuntimeEvent):
    type: Literal["thought"] = "thought"

    thought: str


class IntentRequestEvent(RuntimeEvent):
    type: Literal["intent_request"] = "intent_request"

    intent: str

    target: dict

    params: dict


class OperationEvent(RuntimeEvent):
    type: Literal["operation"] = "operation"

    operation: str

    intent: str


class ObservationEvent(RuntimeEvent):
    type: Literal["observation"] = "observation"

    content: str

    success: bool


class WarningEvent(RuntimeEvent):
    type: Literal["warning"] = "warning"

    message: str


class FinalResultEvent(RuntimeEvent):
    type: Literal["final_result"] = "final_result"

    result: AgentResult
