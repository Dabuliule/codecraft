from __future__ import annotations

import os
from typing import Any

from codecraft.llm.base import LLMConfigError
from codecraft.llm.providers.compatible.base import OpenAICompatibleProvider


class QwenProvider(OpenAICompatibleProvider):
    name = "qwen"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.client = client
        self.api_key = api_key
        self.base_url = base_url

    def _client(self) -> Any:
        return self.client or self._default_client()

    def _default_client(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise LLMConfigError("openai package is not installed") from exc

        api_key = self.api_key or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise LLMConfigError("DASHSCOPE_API_KEY is required for QwenProvider")

        return AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url or os.getenv("QWEN_BASE_URL") or self.DEFAULT_BASE_URL,
        )
