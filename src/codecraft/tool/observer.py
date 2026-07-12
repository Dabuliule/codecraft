from __future__ import annotations

from typing import Any, Protocol

from codecraft.core.turn_context import TurnContext
from codecraft.schema.tool import ToolCall, ToolResult


class ToolResultObserver(Protocol):
    name: str

    async def after_result(
        self,
        call: ToolCall,
        result: ToolResult,
        context: TurnContext,
    ) -> dict[str, Any] | None: ...
