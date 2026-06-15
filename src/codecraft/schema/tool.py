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
    """暴露给模型看的 tool 描述。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    effects: set[ToolEffect] = Field(default_factory=set)
    requires_approval: bool = False
    enabled: bool = True


class ToolCall(BaseModel):
    """模型请求执行某个 tool 时的结构化调用。"""

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """tool 执行完成后回传给模型和 UI 的结果。"""

    success: bool
    content: str
    data: dict[str, Any] | None = None
    error: str | None = None
    suggestion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_error_shape(self) -> ToolResult:
        """保持 success 和 error 字段语义一致。"""
        if self.success and self.error is not None:
            raise ValueError("successful tool results cannot include error")

        if not self.success and not self.error:
            raise ValueError("failed tool results must include error")

        return self
