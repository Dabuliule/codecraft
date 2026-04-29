from typing import Any, Dict, Optional, Literal

from pydantic import BaseModel, Field, model_validator


class Action(BaseModel):
    """LLM 输出动作：要么调用工具，要么给出最终回答。"""

    type: Literal["tool", "final"] = Field(..., description="动作类型")
    tool: Optional[str] = Field(None, description="工具名称")
    tool_input: Optional[Dict[str, Any]] = Field(None, description="工具参数")
    final_answer: Optional[str] = Field(None, description="最终回答")

    @model_validator(mode="after")
    def _validate_action(self) -> "Action":
        if self.type == "tool":
            if not self.tool:
                raise ValueError("type='tool' 时必须提供 tool")
            if self.final_answer:
                raise ValueError("type='tool' 时不能提供 final_answer")
            if self.tool_input is None:
                self.tool_input = {}
            return self

        if not self.final_answer:
            raise ValueError("type='final' 时必须提供 final_answer")
        if self.tool or self.tool_input:
            raise ValueError("type='final' 时不能提供 tool/tool_input")
        return self
