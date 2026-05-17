from typing import Any

from pydantic import BaseModel, Field


class CapabilityCall(BaseModel):
    capability: str = Field(description="能力名称")
    goal: str = Field(description="能力目标")
    constraints: dict[str, Any] = Field(default_factory=dict, description="约束条件")
