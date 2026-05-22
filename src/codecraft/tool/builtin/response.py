from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from codecraft.tool.base import BaseTool, ToolResult


class FinalAnswerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., description="最终返回给用户的答案")


class FinalAnswerTool(BaseTool):
    name = "final_answer"
    description = "结束当前任务并返回最终答案。"
    input_schema = FinalAnswerArgs
    preconditions = ["answer 必须包含最终回复"]
    side_effects = ["结束当前 runtime 任务"]
    tags = {"response"}
    risk_level = "low"

    def execute(self, answer: str) -> ToolResult:
        return ToolResult(
            success=True,
            content=answer,
            data={"final": True, "answer": answer},
        )
