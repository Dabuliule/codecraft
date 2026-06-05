from __future__ import annotations

from typing import Any

from codecraft.llm.base import LLMConfigError
from codecraft.llm.providers.compatible.base import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(self, *, client: Any | None = None) -> None:
        self.client = client

    def _client(self) -> Any:
        return self.client or self._default_client()

    @staticmethod
    def _default_client() -> Any:
        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise LLMConfigError("openai package is not installed") from exc

        return AsyncOpenAI()
