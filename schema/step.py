from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class Step(BaseModel):
    """一次工具调用记录。"""

    tool: str = Field(..., description="工具名称")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    tool_output: Any = Field(..., description="工具输出")
