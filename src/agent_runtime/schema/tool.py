from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """LLM 输出的工具调用请求。"""

    tool: str = Field(description="工具名称，例如 read_file")
    args: Dict[str, Any] = Field(default_factory=dict, description="工具输入参数")
    purpose: Optional[str] = Field(default=None, description="为什么需要调用该工具")

    def pretty(self) -> str:
        return (
            f"Tool: {self.tool}\n"
            f"Args:\n"
            f"{json.dumps(self.args, ensure_ascii=False, indent=2)}\n"
            f"Purpose: {self.purpose or '-'}"
        )


class ToolPlan(BaseModel):
    """Agent 生成、Runtime 负责调度的工具调用计划。"""

    tools: list[ToolCall] = Field(
        default_factory=list,
        description="按顺序处理的工具调用请求",
    )
