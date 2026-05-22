from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from codecraft.llm.base import BaseLLM, LLMConfigError, LLMProviderError, LLMResponse


class QwenLLM(BaseLLM):
    """通义千问适配器（基于阿里云百炼 OpenAI 兼容接口）"""

    def __init__(
            self,
            model: Optional[str] = None,
            api_key: Optional[str] = None,
            max_retries: int = 2,
            retry_delay_seconds: float = 0.5,
    ):
        self.model = self._require_config(
            value=model or os.environ.get("QWEN_MODEL"),
            name="QWEN_MODEL",
            description="Qwen model name",
        )
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)

        resolved_api_key = self._require_config(
            value=api_key or os.getenv("DASHSCOPE_API_KEY"),
            name="DASHSCOPE_API_KEY",
            description="DashScope API key",
        )
        self.client = AsyncOpenAI(
            api_key=resolved_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    async def agenerate(
            self,
            messages: List[Dict[str, Any]],
            **kwargs: Any,
    ) -> LLMResponse:
        request_payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            **kwargs,
        }

        if "extra_body" not in request_payload:
            request_payload["extra_body"] = {"enable_thinking": False}

        response = await self._create_completion(request_payload)

        try:
            return self._build_llm_response(response)
        except Exception as exc:
            raise LLMProviderError("Qwen response parsing failed.") from exc

    async def _create_completion(
            self,
            request_payload: Dict[str, Any],
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await self.client.chat.completions.create(**request_payload)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                if self.retry_delay_seconds:
                    await asyncio.sleep(self.retry_delay_seconds)

        raise LLMProviderError(
            "Qwen completion request failed after "
            f"{self.max_retries + 1} attempt(s)."
        ) from last_error

    def _build_llm_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message

        return LLMResponse(
            content=msg.content,
            finish_reason=choice.finish_reason,
            usage=self._parse_usage(getattr(response, "usage", None)),
        )

    @staticmethod
    def _parse_usage(usage: Any) -> Optional[Dict[str, int]]:
        if not usage:
            return None
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
        }

    @staticmethod
    def _require_config(
            *,
            value: str | None,
            name: str,
            description: str,
    ) -> str:
        resolved = (value or "").strip()
        if resolved:
            return resolved

        raise LLMConfigError(
            f"Missing {description}: set {name} in environment or .env."
        )
