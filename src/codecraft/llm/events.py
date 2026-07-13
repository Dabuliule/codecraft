from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from codecraft.schema.tool import ToolCall


class ModelEventType(StrEnum):
    MESSAGE_DELTA = "message_delta"
    MESSAGE_COMPLETED = "message_completed"
    TOOL_CALL = "tool_call"
    TOKEN_COUNT = "token_count"
    COMPLETED = "completed"
    ERROR = "error"


class ModelTextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class ModelTokenCountPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ModelErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)


class ModelCompletedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


ModelEventPayload = (
    ModelTextPayload
    | ModelTokenCountPayload
    | ModelErrorPayload
    | ModelCompletedPayload
    | ToolCall
)


class ModelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ModelEventType
    payload: ModelEventPayload = Field(default_factory=ModelCompletedPayload)

    @model_validator(mode="before")
    @classmethod
    def validate_payload_for_type(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        event_type = ModelEventType(value.get("type"))
        payload_type: type[BaseModel]
        if event_type in {
            ModelEventType.MESSAGE_DELTA,
            ModelEventType.MESSAGE_COMPLETED,
        }:
            payload_type = ModelTextPayload
        elif event_type == ModelEventType.TOOL_CALL:
            payload_type = ToolCall
        elif event_type == ModelEventType.TOKEN_COUNT:
            payload_type = ModelTokenCountPayload
        elif event_type == ModelEventType.ERROR:
            payload_type = ModelErrorPayload
        else:
            payload_type = ModelCompletedPayload

        normalized = dict(value)
        normalized["payload"] = payload_type.model_validate(value.get("payload", {}))
        return normalized
