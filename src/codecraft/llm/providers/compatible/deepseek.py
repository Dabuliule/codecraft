from __future__ import annotations

from collections.abc import AsyncIterator
import os
from typing import Any

from codecraft.core.turn_context import TurnContext
from codecraft.llm.base import LLMConfigError, LLMProviderError
from codecraft.llm.events import ModelEvent
from codecraft.llm.messages import ModelMessage
from codecraft.llm.providers.compatible.base import OpenAICompatibleProvider
from codecraft.schema.tool import ToolSpec


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        api_key_env: str | None = "DEEPSEEK_API_KEY",
        base_url: str | None = None,
    ) -> None:
        self.client = client
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.base_url = base_url

    def _client(self) -> Any:
        return self.client or self._default_client()

    async def stream(
        self,
        messages: list[ModelMessage],
        tools: list[ToolSpec],
        context: TurnContext,
    ) -> AsyncIterator[ModelEvent]:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": context.model,
            "messages": self._messages_to_chat(messages),
            "stream": True,
        }
        tool_payload = self._tools_to_chat(tools)
        if tool_payload:
            kwargs["tools"] = tool_payload

        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

        if hasattr(response, "__aiter__"):
            async for event in self._events_from_chat_stream(response):
                yield event
            return

        for event in self._events_from_chat_response(response):
            yield event

    def _default_client(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise LLMConfigError("openai package is not installed") from exc

        api_key = self.api_key or (
            os.getenv(self.api_key_env) if self.api_key_env else None
        )
        if not api_key:
            env_name = self.api_key_env or "configured api_key_env"
            raise LLMConfigError(f"{env_name} is required for DeepSeekProvider")

        return AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url
            or os.getenv("DEEPSEEK_BASE_URL")
            or self.DEFAULT_BASE_URL,
        )
