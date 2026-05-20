from __future__ import annotations

from pydantic import BaseModel, Field

from agent_runtime.schema.intent import IntentPlan


class Decision(BaseModel):
    """
    Agent 在当前状态下做出的意图计划决策。

    注意：
    - 输出 intent plan，而不是直接选择执行实现
    - runtime 是 intent 解析、策略校验与调度的唯一 owner
    - decision 是 runtime 的核心驱动单元
    """

    thought: str = Field(
        ...,
        description=(
            "Agent 当前的推理过程。"
            "必须解释为什么生成当前 intent plan。"
            "应该体现当前观察、目标和下一步意图。"
        ),
    )

    plan: IntentPlan = Field(
        ...,
        description=(
            "当前要交给 runtime 解析和调度的意图计划。"
        ),
    )

    expected_outcome: str | None = Field(
        default=None,
        description=(
            "Agent 预期该 intent plan 会得到什么结果。"
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
