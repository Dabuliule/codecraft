from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from schema.action import ToolAction


class Step(BaseModel):
    """
    Agent 单步执行记录。
    """

    step_id: str = Field(
        ...,
        description="step 唯一 ID",
    )

    thought: str = Field(
        ...,
        description="执行该 action 前的 reasoning",
    )

    action: ToolAction = Field(
        ...,
        description="执行动作",
    )

    observation: Any = Field(
        ...,
        description="工具返回结果",
    )

    success: bool = Field(
        ...,
        description="该 step 是否成功",
    )

    summary: str = Field(
        ...,
        description=(
            "该 step 的压缩摘要。"
            "用于 memory compression。"
        ),
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
    )
