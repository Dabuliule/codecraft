from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SessionInputType(StrEnum):
    USER_MESSAGE = "user_message"
    INTERRUPT = "interrupt"
    APPROVAL_DECISION = "approval_decision"
    STEER = "steer"


class SessionInput(BaseModel):
    input_id: str
    type: SessionInputType
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def user_message(cls, input_id: str, text: str) -> SessionInput:
        return cls(
            input_id=input_id,
            type=SessionInputType.USER_MESSAGE,
            payload={"text": text},
        )

    @classmethod
    def approval_decision(
        cls,
        input_id: str,
        *,
        approval_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> SessionInput:
        return cls(
            input_id=input_id,
            type=SessionInputType.APPROVAL_DECISION,
            payload={
                "approval_id": approval_id,
                "approved": approved,
                "reason": reason,
            },
        )
