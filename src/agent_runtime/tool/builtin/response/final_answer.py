from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.tool.base import BaseTool, ToolResult


class FinalAnswerArgs(BaseModel):
    """Final answer 输入参数。"""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(
        ...,
        description="最终返回给用户的答案",
    )


class FinalAnswerTool(BaseTool):
    """结束 Agent 并返回最终答案。"""

    name = "final_answer"
    description = "结束当前任务并返回最终答案"
    args_schema = FinalAnswerArgs

    def _run(self, answer: str) -> ToolResult:
        return ToolResult(
            success=True,
            content=answer,
            data={
                "final": True,
                "answer": answer,
            },
        )
