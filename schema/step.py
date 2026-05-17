from __future__ import annotations

import json

from typing import Any, Dict

from pydantic import BaseModel, Field

from schema import ToolAction
from tool import ToolResult


class Step(BaseModel):
    """一次 action 记录。"""

    action: ToolAction = Field(..., description="ToolAction")
    observation: Any = Field(..., description="Observation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

    def pretty(self) -> str:
        lines = [self.action.pretty(), "📤 Observation:"]

        if isinstance(self.observation, ToolResult):
            if self.observation.content:
                lines.append(self.observation.content)
            elif self.observation.error:
                lines.append(self.observation.error)
            else:
                lines.append("-")
        else:
            try:
                lines.append(json.dumps(self.observation, ensure_ascii=False, indent=2, default=str))
            except Exception:
                lines.append(str(self.observation))

        if self.metadata:
            lines.append("ℹ️ Metadata:")
            lines.append(json.dumps(self.metadata, ensure_ascii=False, indent=2, default=str))

        return "\n".join(lines)
