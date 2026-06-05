from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from codecraft.schema.safety import sanitize_json_value


class RuntimeEventType(StrEnum):
    SESSION_STARTED = "session_started"
    SESSION_CONFIGURED = "session_configured"
    SESSION_RESTORED = "session_restored"

    TURN_STARTED = "turn_started"
    USER_MESSAGE = "user_message"

    ASSISTANT_MESSAGE_DELTA = "assistant_message_delta"
    ASSISTANT_MESSAGE = "assistant_message"

    MODEL_TOOL_CALL = "model_tool_call"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_FINISHED = "tool_call_finished"

    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"

    PATCH_APPLIED = "patch_applied"
    TOKEN_COUNT = "token_count"
    CONTEXT_COMPACTED = "context_compacted"

    ERROR = "error"
    TURN_FINISHED = "turn_finished"
    TURN_ABORTED = "turn_aborted"
    SESSION_CLOSED = "session_closed"


class RuntimeEvent(BaseModel):
    event_id: str
    session_id: str
    turn_id: str | None = None
    seq: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: RuntimeEventType
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload", mode="after")
    @classmethod
    def _sanitize_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        sanitized = sanitize_json_value(value)
        if isinstance(sanitized, dict):
            return sanitized
        return {}
