from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from schema.plan import Plan
from schema.step import Step


class AgentState(BaseModel):
    """Agent Runtime 全局状态。"""

    task: str
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    current_plan: Plan | None = None
    history: list[Step] = Field(default_factory=list)
    final_answer: str | None = None
    done: bool = False
