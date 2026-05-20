from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high"]


class PolicyDecision(BaseModel):
    allowed: bool = Field(description="是否允许执行")
    reason: str = Field(description="策略判定原因")
    requires_approval: bool = Field(
        default=False,
        description="是否需要外部审批",
    )
    suggestion: str | None = Field(
        default=None,
        description="被拒绝时建议使用的更专用意图",
    )
