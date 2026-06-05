from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from codecraft.core.turn_context import TurnContext
from codecraft.llm.base import LLMProvider, LLMProviderError
from codecraft.llm.events import ModelEvent, ModelEventType
from codecraft.llm.messages import ModelMessage
from codecraft.schema.tool import ToolSpec


class OpenAICompatibleProvider(LLMProvider):
    async def stream(
        self,
        messages: list[ModelMessage],
        tools: list[ToolSpec],
        context: TurnContext,
    ) -> AsyncIterator[ModelEvent]:
        client = self._client()
        try:
            response = await client.responses.create(
                model=context.model,
                input=self._messages_to_input(messages),
                tools=self._tools_to_openai(tools),
            )
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

        for event in self._events_from_response(response):
            yield event

    def _client(self) -> Any:
        raise NotImplementedError

    @staticmethod
    def _messages_to_input(messages: list[ModelMessage]) -> list[dict[str, Any]]:
        return [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in messages
        ]

    @staticmethod
    def _tools_to_openai(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in tools
            if tool.enabled
        ]

    def _events_from_response(self, response: Any) -> list[ModelEvent]:
        events: list[ModelEvent] = []
        text = self._response_text(response)
        if text:
            events.append(
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": text},
                )
            )

        for tool_call in self._tool_calls(response):
            events.append(
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload=tool_call,
                )
            )

        usage = self._usage(response)
        if usage:
            events.append(
                ModelEvent(
                    type=ModelEventType.TOKEN_COUNT,
                    payload=usage,
                )
            )

        events.append(ModelEvent(type=ModelEventType.COMPLETED))
        return events

    @staticmethod
    def _response_text(response: Any) -> str:
        output_text = _get(response, "output_text")
        if isinstance(output_text, str):
            return output_text

        parts: list[str] = []
        for item in _get(response, "output", []) or []:
            if _get(item, "type") != "message":
                continue
            for content in _get(item, "content", []) or []:
                text = _get(content, "text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    @staticmethod
    def _tool_calls(response: Any) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for item in _get(response, "output", []) or []:
            item_type = _get(item, "type")
            if item_type not in {"function_call", "tool_call"}:
                continue
            calls.append(
                {
                    "call_id": str(_get(item, "call_id") or _get(item, "id") or ""),
                    "name": str(_get(item, "name") or ""),
                    "arguments": _get(item, "arguments") or {},
                }
            )
        return calls

    @staticmethod
    def _usage(response: Any) -> dict[str, Any]:
        usage = _get(response, "usage")
        if usage is None:
            return {}

        input_tokens = _get(usage, "input_tokens", 0) or 0
        output_tokens = _get(usage, "output_tokens", 0) or 0
        reasoning_tokens = _get(usage, "reasoning_tokens", 0) or 0
        cached_input_tokens = _get(usage, "cached_input_tokens", 0) or 0
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cached_input_tokens": cached_input_tokens,
            "total_tokens": input_tokens + output_tokens + reasoning_tokens,
        }


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
