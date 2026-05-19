import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolAction(BaseModel):
    tool: str = Field(description="工具名称")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    reason: Optional[str] = Field(default=None, description="为什么执行该动作")

    def pretty(self) -> str:
        return (
            f"🔧 Tool: {self.tool}\n"
            f"📥 Input:\n"
            f"{json.dumps(self.tool_input, ensure_ascii=False, indent=2)}\n"
            f"💭 Reason: {self.reason or '-'}"
        )
