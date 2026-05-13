from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Reflection(BaseModel):
    status: Literal[
        "success",
        "continue",
        "retry",
        "replan",
        "abort",
    ] = Field(
        ...,
        description="Reflector 输出的运行时控制信号，用于决定 Runtime 下一步行为。"
    )

    reasoning: str = Field(
        ...,
        min_length=1,
        description="Reflector 对当前执行轨迹的分析与判断原因。"
    )

    missing_information: List[str] = Field(
        default_factory=list,
        description="当前任务缺失的关键信息列表。"
    )

    suggested_fix: Optional[str] = Field(
        default=None,
        description="对下一步修复方向的轻量建议。"
    )
