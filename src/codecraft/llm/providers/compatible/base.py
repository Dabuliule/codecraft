from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any

from codecraft.core.turn_context import TurnContext
from codecraft.llm.base import LLMProvider, LLMProviderError
from codecraft.llm.events import ModelEvent, ModelEventType
from codecraft.llm.messages import ModelMessage, ModelMessageType
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
                stream=True,
            )
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

        if hasattr(response, "__aiter__"):
            async for event in self._events_from_stream(response):
                yield event
            return

        for model_event in self._events_from_response(response):
            yield model_event

    def _client(self) -> Any:
        raise NotImplementedError

    @staticmethod
    def _messages_to_input(messages: list[ModelMessage]) -> list[dict[str, Any]]:
        return [_message_to_input_item(message) for message in messages]

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

    @staticmethod
    def _messages_to_chat(messages: list[ModelMessage]) -> list[dict[str, Any]]:
        return [_message_to_chat_item(message) for message in messages]

    @staticmethod
    def _tools_to_chat(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
            if tool.enabled
        ]

    async def _events_from_chat_stream(self, stream: Any) -> AsyncIterator[ModelEvent]:
        tool_call_parts: dict[int, dict[str, Any]] = {}
        latest_usage: dict[str, Any] = {}

        async for chunk in stream:
            usage = self._chat_usage(chunk)
            if usage:
                latest_usage = usage

            for choice in _get(chunk, "choices", []) or []:
                delta = _get(choice, "delta", {}) or {}
                content = _get(delta, "content")
                if isinstance(content, str) and content:
                    yield ModelEvent(
                        type=ModelEventType.MESSAGE_DELTA,
                        payload={"text": content},
                    )

                for raw_tool_call in _get(delta, "tool_calls", []) or []:
                    index = int(_get(raw_tool_call, "index", 0) or 0)
                    part = tool_call_parts.setdefault(
                        index,
                        {"call_id": "", "name": "", "arguments": []},
                    )
                    call_id = _get(raw_tool_call, "id")
                    if isinstance(call_id, str) and call_id:
                        part["call_id"] = call_id
                    function = _get(raw_tool_call, "function", {}) or {}
                    name = _get(function, "name")
                    if isinstance(name, str) and name:
                        part["name"] = name
                    arguments = _get(function, "arguments")
                    if isinstance(arguments, str) and arguments:
                        part["arguments"].append(arguments)

        for index in sorted(tool_call_parts):
            part = tool_call_parts[index]
            yield ModelEvent(
                type=ModelEventType.TOOL_CALL,
                payload={
                    "call_id": str(part["call_id"]),
                    "name": str(part["name"]),
                    "arguments": _parse_arguments("".join(part["arguments"])),
                },
            )

        if latest_usage:
            yield ModelEvent(type=ModelEventType.TOKEN_COUNT, payload=latest_usage)

        yield ModelEvent(type=ModelEventType.COMPLETED)

    def _events_from_chat_response(self, response: Any) -> list[ModelEvent]:
        events: list[ModelEvent] = []
        usage = self._chat_usage(response)

        for choice in _get(response, "choices", []) or []:
            message = _get(choice, "message", {}) or {}
            content = _get(message, "content")
            if isinstance(content, str) and content:
                events.append(
                    ModelEvent(
                        type=ModelEventType.MESSAGE_COMPLETED,
                        payload={"text": content},
                    )
                )
            for tool_call in _chat_tool_calls(message):
                events.append(
                    ModelEvent(
                        type=ModelEventType.TOOL_CALL,
                        payload=tool_call,
                    )
                )

        if usage:
            events.append(ModelEvent(type=ModelEventType.TOKEN_COUNT, payload=usage))
        events.append(ModelEvent(type=ModelEventType.COMPLETED))
        return events

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

    async def _events_from_stream(self, stream: Any) -> AsyncIterator[ModelEvent]:
        completed = False
        emitted_delta = False

        async for raw_event in stream:
            event_type = str(_get(raw_event, "type", ""))

            if event_type in {
                "response.output_text.delta",
                "output_text.delta",
                "message_delta",
            }:
                delta = _get(raw_event, "delta") or _get(raw_event, "text") or ""
                if isinstance(delta, str) and delta:
                    emitted_delta = True
                    yield ModelEvent(
                        type=ModelEventType.MESSAGE_DELTA,
                        payload={"text": delta},
                    )
                continue

            if event_type in {
                "response.output_item.done",
                "output_item.done",
            }:
                item = _get(raw_event, "item")
                if item is None:
                    continue
                text = self._response_text({"output": [item]})
                if text and not emitted_delta:
                    yield ModelEvent(
                        type=ModelEventType.MESSAGE_COMPLETED,
                        payload={"text": text},
                    )
                for tool_call in self._tool_calls({"output": [item]}):
                    yield ModelEvent(type=ModelEventType.TOOL_CALL, payload=tool_call)
                continue

            if event_type in {
                "response.completed",
                "response.done",
                "completed",
            }:
                response = _get(raw_event, "response", raw_event)
                usage = self._usage(response)
                if usage:
                    yield ModelEvent(type=ModelEventType.TOKEN_COUNT, payload=usage)
                yield ModelEvent(type=ModelEventType.COMPLETED)
                completed = True
                continue

            if event_type in {
                "response.failed",
                "response.error",
                "error",
            }:
                error = _get(raw_event, "error", raw_event)
                message = _get(error, "message", str(error))
                yield ModelEvent(
                    type=ModelEventType.ERROR,
                    payload={"message": str(message)},
                )

        if not completed:
            yield ModelEvent(type=ModelEventType.COMPLETED)

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
                    "arguments": _parse_arguments(_get(item, "arguments") or {}),
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

    @staticmethod
    def _chat_usage(response: Any) -> dict[str, Any]:
        usage = _get(response, "usage")
        if usage is None:
            return {}

        input_tokens = (
            _get(usage, "input_tokens", None)
            if _get(usage, "input_tokens", None) is not None
            else _get(usage, "prompt_tokens", 0)
        ) or 0
        output_tokens = (
            _get(usage, "output_tokens", None)
            if _get(usage, "output_tokens", None) is not None
            else _get(usage, "completion_tokens", 0)
        ) or 0
        reasoning_tokens = _get(usage, "reasoning_tokens", 0) or 0
        total_tokens = (
            _get(usage, "total_tokens", None)
            if _get(usage, "total_tokens", None) is not None
            else input_tokens + output_tokens + reasoning_tokens
        ) or 0
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cached_input_tokens": _get(usage, "cached_input_tokens", 0) or 0,
            "total_tokens": total_tokens,
        }


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _message_to_input_item(message: ModelMessage) -> dict[str, Any]:
    if message.type == ModelMessageType.FUNCTION_CALL:
        return {
            "type": "function_call",
            "call_id": message.tool_call_id or "",
            "name": message.name or "",
            "arguments": _arguments_to_json(message),
        }

    if message.type == ModelMessageType.FUNCTION_CALL_OUTPUT:
        return {
            "type": "function_call_output",
            "call_id": message.tool_call_id or "",
            "output": message.content,
        }

    return {
        "role": message.role.value,
        "content": message.content,
    }


def _message_to_chat_item(message: ModelMessage) -> dict[str, Any]:
    if message.type == ModelMessageType.FUNCTION_CALL:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": message.tool_call_id or "",
                    "type": "function",
                    "function": {
                        "name": message.name or "",
                        "arguments": _arguments_to_json(message),
                    },
                }
            ],
        }

    if message.type == ModelMessageType.FUNCTION_CALL_OUTPUT:
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id or "",
            "content": message.content,
        }

    return {
        "role": message.role.value,
        "content": message.content,
    }


def _chat_tool_calls(message: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for tool_call in _get(message, "tool_calls", []) or []:
        function = _get(tool_call, "function", {}) or {}
        calls.append(
            {
                "call_id": str(_get(tool_call, "id") or ""),
                "name": str(_get(function, "name") or ""),
                "arguments": _parse_arguments(_get(function, "arguments") or {}),
            }
        )
    return calls


def _arguments_to_json(message: ModelMessage) -> str:
    if message.arguments is not None:
        return json.dumps(
            message.arguments,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    try:
        parsed = json.loads(message.content)
    except json.JSONDecodeError:
        return message.content

    if isinstance(parsed, dict):
        return json.dumps(
            parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    return message.content


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed

    return {}
