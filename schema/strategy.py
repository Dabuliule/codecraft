from __future__ import annotations

from pydantic import BaseModel, Field


class Strategy(BaseModel):
    """
    Agent 当前的高层执行策略。

    注意：
    - strategy 不是固定计划
    - strategy 可以动态调整
    - strategy 用于维持长期目标一致性
    """

    objective: str = Field(
        ...,
        description=(
            "当前任务的核心目标。"
            "应保持稳定，不应频繁变化。"
        ),
    )

    current_focus: str = Field(
        ...,
        description=(
            "当前阶段正在重点处理的问题。"
            "focus 会随着执行动态变化。"
        ),
    )

    approach: str = Field(
        ...,
        description=(
            "当前采用的整体策略。"
            "例如："
            "先理解项目结构，再定位测试失败原因。"
        ),
    )

    known_constraints: list[str] = Field(
        default_factory=list,
        description=(
            "当前已知限制条件。"
            "例如："
            "- 不要修改 public API"
            "- 不能删除数据库字段"
        ),
    )

    discovered_facts: list[str] = Field(
        default_factory=list,
        description=(
            "执行过程中发现的重要事实。"
            "用于长期上下文维持。"
        ),
    )

    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "当前仍未解决的问题。"
            "这些问题会驱动后续 action。"
        ),
    )

    completed_milestones: list[str] = Field(
        default_factory=list,
        description=(
            "已经完成的重要阶段性目标。"
        ),
    )
