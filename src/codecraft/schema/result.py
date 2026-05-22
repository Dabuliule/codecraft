from __future__ import annotations

from pydantic import BaseModel, Field

from codecraft.schema.step import Step


class AgentResult(BaseModel):
    """
    Agent Runtime 最终执行结果。
    """
    success: bool = Field(
        ...,
        description="任务是否成功完成",
    )

    answer: str | None = Field(
        default=None,
        description="最终回答",
    )

    steps: list[Step] = Field(
        default_factory=list,
        description="执行轨迹",
    )

    memory: list[str] = Field(
        default_factory=list,
        description="压缩后的长期记忆",
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="运行时警告",
    )

    total_steps: int = Field(
        default=0,
        description="总执行步数",
    )
