from __future__ import annotations

from collections.abc import AsyncIterator

from codecraft.core.turn_context import TurnContext
from codecraft.llm.base import LLMProvider
from codecraft.llm.events import ModelEvent
from codecraft.llm.messages import ModelMessage
from codecraft.schema.tool import ToolSpec


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, script: list[ModelEvent] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[tuple[list[ModelMessage], list[ToolSpec], TurnContext]] = []

    async def stream(
        self,
        messages: list[ModelMessage],
        tools: list[ToolSpec],
        context: TurnContext,
    ) -> AsyncIterator[ModelEvent]:
        self.calls.append((messages, tools, context))
        while self.script:
            yield self.script.pop(0)
