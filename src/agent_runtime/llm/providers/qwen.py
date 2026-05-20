from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from agent_runtime.llm.base import BaseLLM, LLMResponse


class QwenLLM(BaseLLM):
    """通义千问适配器（基于阿里云百炼 OpenAI 兼容接口）"""

    def __init__(
            self,
            model: Optional[str] = None,
            api_key: Optional[str] = None,
    ):
        self.model = model or os.environ.get("QWEN_MODEL")
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
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

        response = await self.client.chat.completions.create(**request_payload)
        return self._build_llm_response(response)

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
