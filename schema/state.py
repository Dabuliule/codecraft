from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .step import Step


class AgentState(BaseModel):
    """Agent 运行状态。"""

    task: str
    history: List[Step] = Field(default_factory=list)
    current_step: int = 0
    max_steps: int = 10
    done: bool = False
