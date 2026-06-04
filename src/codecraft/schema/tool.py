from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ToolEffect(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    PROCESS_EXEC = "process_exec"
    NETWORK = "network"
    EXTERNAL = "external"


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    effects: set[ToolEffect] = Field(default_factory=set)
    requires_approval: bool = False
    enabled: bool = True


class ToolCall(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    success: bool
    content: str
    data: dict[str, Any] | None = None
    error: str | None = None
    suggestion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_error_shape(self) -> ToolResult:
        if self.success and self.error is not None:
            raise ValueError("successful tool results cannot include error")

        if not self.success and not self.error:
            raise ValueError("failed tool results must include error")

        return self
