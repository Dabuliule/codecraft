from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ModelRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ModelMessageType(StrEnum):
    MESSAGE = "message"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"


class ModelMessage(BaseModel):
    type: ModelMessageType = ModelMessageType.MESSAGE
    role: ModelRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    arguments: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
