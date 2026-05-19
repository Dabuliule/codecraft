from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_runtime.schema.action import ToolAction
from agent_runtime.tool.base import ToolResult


class Step(BaseModel):
    """
    Agent 单步执行记录。
    """

    step_id: str = Field(
        ...,
        description="step 唯一 ID",
    )

    thought: str = Field(
        ...,
        description="执行该 action 前的 reasoning",
    )

    action: ToolAction = Field(
        ...,
        description="执行动作",
    )

    observation: Any = Field(
        ...,
        description="工具返回结果",
    )

    success: bool = Field(
        ...,
        description="该 step 是否成功",
    )

    summary: str = Field(
        ...,
        description=(
            "该 step 的压缩摘要。"
            "用于 memory compression。"
        ),
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
    )

    def pretty(self) -> str:

        lines: list[str] = [
            "=" * 60,
            f"STEP {self.step_id}",
            "=" * 60,
            f"Success   : {self.success}",
            f"CreatedAt : {self.created_at.isoformat()}",
            "",
            "Thought:",
            self.thought,
            "",
            "Action:",
            self.action.pretty(),
            "",
            "Observation:",
        ]

        if isinstance(self.observation, ToolResult):
            if self.observation.success:
                content = (
                    self.observation.content
                    if self.observation.content
                    else "-"
                )

                lines.append(str(content))
            else:
                lines.append(
                    f"ERROR: {self.observation.error}"
                )

                if self.observation.suggestion:
                    lines.append("")
                    lines.append("Suggestion:")
                    lines.append(
                        self.observation.suggestion
                    )
        else:
            try:
                lines.append(
                    json.dumps(
                        self.observation,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                )
            except Exception:
                lines.append(
                    str(self.observation)
                )

        lines.extend(
            [
                "",
                "Summary:",
                self.summary,
            ]
        )

        return "\n".join(lines)
