from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from codecraft.core.turn_context import TurnContext
from codecraft.schema.tool import ToolCall, ToolEffect, ToolResult, ToolSpec


class ToolContext(BaseModel):
    """tool 执行时可读取的 turn 上下文和审批状态。"""

    context: TurnContext
    call: ToolCall
    approved: bool = False


class BaseTool(ABC):
    """所有内置和扩展 tool 的基类。"""

    name: str
    description: str
    args_schema: type[BaseModel]
    effects: set[ToolEffect] = set()
    requires_approval: bool = False

    def spec(self) -> ToolSpec:
        """生成可以传给模型的 ToolSpec。"""
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.args_schema.model_json_schema(),
            effects=self.effects,
            requires_approval=self.requires_approval,
        )

    @abstractmethod
    async def arun(self, args: BaseModel, context: ToolContext) -> ToolResult: ...
