from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from codecraft.core.turn_context import TurnContext
from codecraft.schema.tool import ToolCall, ToolEffect, ToolResult, ToolSpec


class ToolContext(BaseModel):
    context: TurnContext
    call: ToolCall


class BaseTool(ABC):
    name: str
    description: str
    args_schema: type[BaseModel]
    effects: set[ToolEffect] = set()
    requires_approval: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.args_schema.model_json_schema(),
            effects=self.effects,
            requires_approval=self.requires_approval,
        )

    @abstractmethod
    async def arun(self, args: BaseModel, context: ToolContext) -> ToolResult:
        ...
