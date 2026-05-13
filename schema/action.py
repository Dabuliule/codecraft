from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolAction(BaseModel):
    tool: str = Field(description="工具名称")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    reason: Optional[str] = Field(default=None, description="为什么执行该动作")
