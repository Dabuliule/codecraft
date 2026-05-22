from __future__ import annotations

from pydantic import BaseModel, Field

from codecraft.schema.tool import ToolPlan


class Decision(BaseModel):
    """
    Agent 在当前状态下做出的工具调用计划决策。

    注意：
    - 输出 tool plan
    - runtime 是工具策略校验与调度的唯一 owner
    - decision 是 runtime 的核心驱动单元
    """

    thought: str = Field(
        ...,
        description=(
            "Agent 当前的推理过程。"
            "必须解释为什么生成当前 tool plan。"
            "应该体现当前观察、目标和下一步工具调用。"
        ),
    )

    plan: ToolPlan = Field(
        ...,
        description=(
            "当前要交给 runtime 调度的工具调用计划。"
        ),
    )

    expected_outcome: str | None = Field(
        default=None,
        description=(
            "Agent 预期该 tool plan 会得到什么结果。"
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
