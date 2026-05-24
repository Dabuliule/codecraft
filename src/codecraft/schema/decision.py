from __future__ import annotations

from pydantic import BaseModel, Field

from codecraft.schema.tool import ToolCall


class Decision(BaseModel):
    """
    Agent 在当前状态下做出的单步工具调用决策。

    注意：
    - 每次只输出一个 tool call
    - runtime 是工具策略校验与执行的唯一 owner
    - decision 是 runtime 的核心驱动单元
    """

    rationale: str = Field(
        ...,
        description=(
            "Agent 当前决策的简短理由。"
            "应该体现当前观察、目标和下一步工具调用。"
        ),
    )

    tool_call: ToolCall = Field(
        ...,
        description=(
            "当前要交给 runtime 执行的单个工具调用。"
        ),
    )

    expected_outcome: str | None = Field(
        default=None,
        description=(
            "Agent 预期该 tool call 会得到什么结果。"
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
