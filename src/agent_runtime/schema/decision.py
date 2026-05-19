from __future__ import annotations

from pydantic import BaseModel, Field

from agent_runtime.schema.action import ToolAction


class Decision(BaseModel):
    """
    Agent 在当前状态下做出的“单步决策”。

    注意：
    - 一次只允许一个 action
    - runtime 每执行一步后都必须重新决策
    - decision 是 runtime 的核心驱动单元
    """

    thought: str = Field(
        ...,
        description=(
            "Agent 当前的推理过程。"
            "必须解释为什么选择当前 action。"
            "应该体现当前观察、目标和下一步意图。"
        ),
    )

    action: ToolAction = Field(
        ...,
        description=(
            "当前唯一允许执行的动作。"
            "runtime 执行完成后必须重新进入下一轮 decision。"
        ),
    )

    expected_outcome: str | None = Field(
        default=None,
        description=(
            "Agent 预期该 action 会得到什么结果。"
            "用于后续 observation 对比与 trajectory correction。"
        ),
    )

    strategy_note: str | None = Field(
        default=None,
        description=(
            "对当前整体策略的补充说明。"
            "不是 executable plan，"
            "而是当前阶段目标与方向。"
        ),
    )

    is_terminal: bool = Field(
        default=False,
        description=(
            "当前 decision 是否意味着任务结束。"
            "通常仅 final_answer 为 true。"
        ),
    )
