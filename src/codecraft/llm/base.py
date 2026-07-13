from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from codecraft.core.turn_context import TurnContext
from codecraft.core.errors import ModelProviderError
from codecraft.llm.events import ModelEvent
from codecraft.llm.messages import ModelMessage
from codecraft.schema.tool import ToolSpec


class LLMConfigError(RuntimeError):
    """LLM provider 缺少本地配置时抛出。"""


class LLMProviderError(ModelProviderError):
    """LLM provider 调用失败时抛出。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="model_error")


class LLMProtocolError(ModelProviderError):
    """LLM provider 违反内部事件协议时抛出。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="model_protocol_error")


class LLMProvider(ABC):
    """所有模型 provider 的统一接口。"""

    name: str

    @abstractmethod
    async def stream(
        self,
        messages: list[ModelMessage],
        tools: list[ToolSpec],
        context: TurnContext,
    ) -> AsyncIterator[ModelEvent]: ...
