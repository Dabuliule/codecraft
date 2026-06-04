from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from codecraft.core.turn_context import TurnContext
from codecraft.llm.events import ModelEvent
from codecraft.llm.messages import ModelMessage
from codecraft.schema.tool import ToolSpec


class LLMConfigError(RuntimeError):
    """Raised when an LLM provider is missing required local configuration."""


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider call fails."""


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def stream(
        self,
        messages: list[ModelMessage],
        tools: list[ToolSpec],
        context: TurnContext,
    ) -> AsyncIterator[ModelEvent]:
        ...
