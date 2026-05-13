from pydantic import BaseModel, Field

from schema.action import ToolAction


class Plan(BaseModel):
    actions: list[ToolAction] = Field(default_factory=list, description="执行计划")
