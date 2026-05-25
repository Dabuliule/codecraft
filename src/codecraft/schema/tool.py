from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high"]


class ToolCall(BaseModel):
    """LLM 输出的工具调用请求。"""

    tool: str = Field(description="工具名称，例如 read_file")
    args: Dict[str, Any] = Field(default_factory=dict, description="工具输入参数")
    purpose: Optional[str] = Field(default=None, description="为什么需要调用该工具")
