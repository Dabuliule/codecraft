from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

from schema import ToolAction


class Step(BaseModel):
    """一次 action 记录。"""

    action: ToolAction = Field(..., description="ToolAction")
    observation: Any = Field(..., description="Observation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
