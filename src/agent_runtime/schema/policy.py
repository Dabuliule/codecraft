from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high"]
PolicyAction = Literal["allow", "deny", "require_approval"]


class PolicyDecision(BaseModel):
    action: PolicyAction = Field(
        ...,
        description="策略动作：允许、拒绝或需要外部审批",
    )
    reason: str = Field(description="策略判定原因")
    suggestion: str | None = Field(
        default=None,
        description="被拒绝时建议使用的更专用意图",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="结构化策略上下文，供 trace、CLI 和测试使用",
    )

    @classmethod
    def allow(
            cls,
            reason: str,
            data: dict[str, Any] | None = None,
    ) -> "PolicyDecision":
        return cls(
            action="allow",
            reason=reason,
            data=data or {},
        )

    @classmethod
    def deny(
            cls,
            reason: str,
            suggestion: str | None = None,
            data: dict[str, Any] | None = None,
    ) -> "PolicyDecision":
        return cls(
            action="deny",
            reason=reason,
            suggestion=suggestion,
            data=data or {},
        )

    @classmethod
    def require_approval(
            cls,
            reason: str,
            suggestion: str | None = None,
            data: dict[str, Any] | None = None,
    ) -> "PolicyDecision":
        return cls(
            action="require_approval",
            reason=reason,
            suggestion=suggestion,
            data=data or {},
        )
