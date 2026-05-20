from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.operation.base import BaseOperation, OperationResult


class FinalAnswerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., description="最终返回给用户的答案")


class FinalAnswerOperation(BaseOperation):
    name = "final_answer"
    intent = "response.final"
    description = "结束当前任务并返回最终答案。"
    input_schema = FinalAnswerArgs
    preconditions = ["answer 必须包含最终回复"]
    side_effects = ["结束当前 runtime 任务"]
    tags = {"response"}
    risk_level = "low"

    def execute(self, answer: str) -> OperationResult:
        return OperationResult(
            success=True,
            content=answer,
            data={"final": True, "answer": answer},
        )
