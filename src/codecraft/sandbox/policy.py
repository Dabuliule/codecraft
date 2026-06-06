from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from codecraft.schema.tool import ToolEffect


class SandboxMode(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class SandboxPolicy(BaseModel):
    mode: SandboxMode
    workspace_roots: list[Path]
    network_access: bool = False
    writable_roots: list[Path] = Field(default_factory=list)

    def evaluate_effects(self, effects: set[ToolEffect]) -> "SandboxEvaluation":
        if ToolEffect.NETWORK in effects and not self.network_access:
            return SandboxEvaluation.deny(
                "network access is disabled by sandbox policy",
                denied_effect=ToolEffect.NETWORK,
            )

        if self.mode == SandboxMode.READ_ONLY:
            denied = effects - {ToolEffect.READ_ONLY}
            if denied:
                return SandboxEvaluation.deny(
                    "read_only sandbox allows read-only tools only",
                    denied_effect=sorted(denied)[0],
                )

        return SandboxEvaluation(
            allowed=True,
            reason="tool effects are allowed by sandbox policy",
        )


class SandboxEvaluation(BaseModel):
    allowed: bool
    reason: str
    denied_effect: ToolEffect | None = None

    @classmethod
    def deny(cls, reason: str, *, denied_effect: ToolEffect) -> "SandboxEvaluation":
        return cls(
            allowed=False,
            reason=reason,
            denied_effect=denied_effect,
        )
