from __future__ import annotations

import os
from typing import Any

from codecraft.llm.base import LLMConfigError
from codecraft.llm.providers.compatible.base import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        api_key_env: str | None = "OPENAI_API_KEY",
        base_url: str | None = None,
    ) -> None:
        self.client = client
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.base_url = base_url

    def _client(self) -> Any:
        return self.client or self._default_client()

    def _default_client(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise LLMConfigError("openai package is not installed") from exc

        kwargs: dict[str, Any] = {}
        api_key = self.api_key or (
            os.getenv(self.api_key_env) if self.api_key_env else None
        )
        if api_key:
            kwargs["api_key"] = api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url

        return AsyncOpenAI(**kwargs)
