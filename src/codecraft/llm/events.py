from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ModelEventType(StrEnum):
    MESSAGE_DELTA = "message_delta"
    MESSAGE_COMPLETED = "message_completed"
    TOOL_CALL = "tool_call"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOKEN_COUNT = "token_count"
    COMPLETED = "completed"
    ERROR = "error"


class ModelEvent(BaseModel):
    type: ModelEventType
    payload: dict[str, Any] = Field(default_factory=dict)
