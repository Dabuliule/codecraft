from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from schema.decision import Decision
from schema.step import Step
from schema.strategy import Strategy


class AgentState(BaseModel):
    """
    Agent Runtime 全局状态。

    注意：
    - state 是 runtime 的唯一真实状态源
    - 所有 decision 都必须基于 state
    - state 不应依赖固定 plan
    """

    trace_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="当前运行链路 ID",
    )

    task: str = Field(
        ...,
        description="用户原始任务",
    )

    strategy: Strategy = Field(
        ...,
        description="当前高层执行策略",
    )

    current_decision: Decision | None = Field(
        default=None,
        description="当前 step decision",
    )

    recent_steps: list[Step] = Field(
        default_factory=list,
        description=(
            "最近执行步骤。"
            "仅保留短期 trajectory。"
        ),
    )

    memory: list[str] = Field(
        default_factory=list,
        description=(
            "长期压缩记忆。"
            "用于存储关键事实与结论。"
        ),
    )

    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "运行时警告。"
            "例如连续失败、trajectory drift 等。"
        ),
    )

    final_answer: str | None = Field(
        default=None,
        description="最终答案",
    )

    done: bool = Field(
        default=False,
        description="任务是否完成",
    )
