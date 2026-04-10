"""ReAct 风格 Agent，支持工具调用。"""

import json
import re
from typing import Any, Iterable, Iterator

from core.agent import Agent
from core.exceptions import AgentException, HelloAgentsException, ToolException
from core.message import Message
from tools.base import Tool
from tools.registry import ToolRegistry


class ReActAgent(Agent):
    """遵循 Thought/Action/Observation 循环的 Agent。"""

    def __init__(
            self,
            name: str,
            llm,
            system_prompt: str | None = None,
            history_limit: int = 100,
            tools: Iterable[Tool] | None = None,
            tool_registry: ToolRegistry | None = None,
            max_iterations: int = 8,
            max_tool_failures: int = 3,
    ):
        super().__init__(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            history_limit=history_limit,
            tools=tools,
            tool_registry=tool_registry,
        )
        self.max_iterations = max_iterations
        if max_tool_failures < 1:
            raise ValueError("max_tool_failures 必须大于 0")
        self.max_tool_failures = max_tool_failures
        self._consecutive_tool_failures = 0
        self._last_failed_signature: str | None = None

    def run(self, input_text: str, **kwargs: Any) -> str:
        """非流式执行，返回最终答案。"""
        user_text = self._normalize_input(input_text)
        self.add_message(Message(role="user", content=user_text))
        return self._reasoning_loop(**kwargs)

    def run_stream(self, input_text: str, **kwargs: Any) -> Iterator[str]:
        """流式执行，产出模型输出和观察结果。"""
        user_text = self._normalize_input(input_text)
        self.add_message(Message(role="user", content=user_text))
        yield from self._reasoning_loop_stream(**kwargs)

    def _reasoning_loop(self, **kwargs: Any) -> str:
        for _ in range(self.max_iterations):
            tool_result = self._invoke_with_tools(**kwargs)
            if tool_result["used_tool_calling"]:
                content = tool_result["content"].strip()
                tool_calls = tool_result["tool_calls"]
                if tool_calls:
                    self.add_message(
                        Message(
                            role="assistant",
                            content=content,
                            metadata={"tool_calls": tool_calls},
                        )
                    )
                    self._execute_tool_calls(tool_calls)
                    continue
                if content:
                    self.add_message(Message(role="assistant", content=content))
                    return content
                raise AgentException("ReActAgent 未收到有效内容或工具调用。")

            response = tool_result["content"].strip()
            if not response:
                continue
            self.add_message(Message(role="assistant", content=response))

            parsed = self._parse_json_response(response)
            if parsed.get("type") == "final":
                return parsed["final"]

            action = parsed.get("action") or {}
            tool_name = action.get("name")
            tool_params = action.get("params") or {}
            if not tool_name:
                raise AgentException("ReActAgent 未提供可执行的动作。")

            self._call_tool_with_guard(tool_name, tool_params)

        raise AgentException("ReActAgent 超过最大迭代次数仍未给出最终答案。")

    def _reasoning_loop_stream(self, **kwargs: Any) -> Iterator[str]:
        for _ in range(self.max_iterations):
            tool_result = self._invoke_with_tools(**kwargs)
            if tool_result["used_tool_calling"]:
                content = tool_result["content"].strip()
                tool_calls = tool_result["tool_calls"]
                if tool_calls:
                    self.add_message(
                        Message(
                            role="assistant",
                            content=content,
                            metadata={"tool_calls": tool_calls},
                        )
                    )
                    if content:
                        yield content
                    for result in self._execute_tool_calls(tool_calls):
                        yield f"\n观察结果: {result}\n"
                    continue
                if content:
                    self.add_message(Message(role="assistant", content=content))
                    yield content
                    return
                raise AgentException("ReActAgent 未收到有效内容或工具调用。")

            chunks: list[str] = []
            try:
                for chunk in self.llm.stream_invoke(self._build_messages(tool_calling=False), **kwargs):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    yield chunk
            except HelloAgentsException as exc:
                raise AgentException(f"ReActAgent 流式调用失败: {exc}") from exc

            response = "".join(chunks).strip()
            if not response:
                continue

            self.add_message(Message(role="assistant", content=response))

            parsed = self._parse_json_response(response)
            if parsed.get("type") == "final":
                return

            action = parsed.get("action") or {}
            tool_name = action.get("name")
            tool_params = action.get("params") or {}
            if not tool_name:
                raise AgentException("ReActAgent 未提供可执行的动作。")

            result = self._call_tool_with_guard(tool_name, tool_params)
            yield f"\n观察结果: {result}\n"

        raise AgentException("ReActAgent 超过最大迭代次数仍未给出最终答案。")

    def _invoke_with_tools(self, **kwargs: Any) -> dict[str, Any]:
        try:
            tools = self.tool_registry.export_openai_tools()
            return self.llm.invoke_with_tools(
                self._build_messages(tool_calling=True),
                tools,
                **kwargs,
            )
        except HelloAgentsException as exc:
            raise AgentException(f"ReActAgent 调用 LLM 失败: {exc}") from exc

    def _build_messages(self, tool_calling: bool) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        system_blocks: list[str] = []

        if self.system_prompt:
            system_blocks.append(self.system_prompt)

        if tool_calling:
            system_blocks.append("你可以使用可用工具获取信息或执行操作。")
            system_blocks.append(self._tool_retry_hint())
        else:
            system_blocks.append(self._json_format_hint())

        if system_blocks:
            messages.append({"role": "system", "content": "\n\n".join(system_blocks)})

        for message in self.get_history():
            if tool_calling:
                messages.append(message.to_dict())
            else:
                # TODO: tool 角色不适配当前调用方式，转为 assistant 的 Observation
                if message.role == "tool":
                    messages.append({"role": "assistant", "content": f"Observation: {message.content}"})
                else:
                    messages.append(message.to_dict())

        return messages

    def _json_format_hint(self) -> str:
        tool_section = f"\n\n【可用工具】\n{self._build_tool_hint()}\n"
        return (
            "你必须严格输出 JSON，且只能输出 JSON 对象，不要包含额外文本或代码块。\n\n"
            "响应必须符合以下 JSON Schema：\n"
            "{\n"
            "  \"type\": \"action\" | \"final\",\n"
            "  \"action\": {\n"
            "    \"name\": \"<工具名称>\",\n"
            "    \"params\": { <工具参数> }\n"
            "  },\n"
            "  \"final\": \"<最终答案>\"\n"
            "}\n\n"
            "规则：\n"
            "- 当 type=action 时，必须提供 action.name 和 action.params\n"
            "- 当 type=final 时，必须提供 final 且禁止提供 action\n"
            "- 只输出 JSON（使用双引号），不得包含注释或 trailing comma\n"
            "- 如果收到工具错误 Observation，下一轮必须修正工具名或参数，不得原样重试\n"
            f"{tool_section}\n"
            "请严格遵守以上规则进行输出。"
        )

    @staticmethod
    def _tool_retry_hint() -> str:
        return (
            "如果工具返回错误，请根据错误信息修正参数后再重试；"
            "禁止重复提交完全相同的错误调用。"
        )

    def _execute_tool_calls(self, tool_calls: list[Any]) -> list[Any]:
        results: list[Any] = []
        for call in tool_calls:
            function = getattr(call, "function", None)
            if function is None:
                function = call.get("function") if isinstance(call, dict) else None
            if function is None:
                raise AgentException("工具调用缺少 function 字段。")

            name = getattr(function, "name", None) or function.get("name")
            if not name:
                raise AgentException("工具调用缺少 function.name。")

            arguments = getattr(function, "arguments", None) or function.get("arguments") or "{}"
            tool_call_id = getattr(call, "id", None) or call.get("id") if isinstance(call, dict) else None

            if isinstance(arguments, str):
                try:
                    params = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise AgentException(f"工具调用参数 JSON 解析失败: {exc}") from exc
            elif isinstance(arguments, dict):
                params = arguments
            else:
                raise AgentException("工具调用参数必须是 JSON 字符串或对象。")

            if not isinstance(params, dict):
                raise AgentException("工具调用参数必须是 JSON 对象。")

            results.append(self._call_tool_with_guard(name, params, tool_call_id=tool_call_id))
        return results

    def _call_tool_with_guard(
            self,
            tool_name: str,
            tool_params: dict[str, Any],
            tool_call_id: str | None = None,
    ) -> Any:
        try:
            result = self.call_tool(tool_name, tool_params, tool_call_id=tool_call_id)
            self._consecutive_tool_failures = 0
            self._last_failed_signature = None
            return result
        except ToolException as exc:
            signature = self._build_call_signature(tool_name, tool_params)
            repeated = signature == self._last_failed_signature
            self._last_failed_signature = signature
            self._consecutive_tool_failures += 1

            schema_hint = self._get_tool_schema_hint(tool_name)
            repeat_hint = "请修正后重试，不要重复同一参数。" if repeated else "请根据错误信息修正参数后重试。"
            error_text = (
                f"工具 {tool_name} 调用失败: {exc}. {repeat_hint}"
                + (f" schema: {schema_hint}" if schema_hint else "")
            )
            self.add_message(
                Message(
                    role="tool",
                    content=error_text,
                    metadata={
                        "tool": tool_name,
                        "params": tool_params,
                        "tool_call_id": tool_call_id,
                        "error": True,
                    },
                )
            )

            if self._consecutive_tool_failures >= self.max_tool_failures:
                raise AgentException(
                    f"ReActAgent 连续 {self._consecutive_tool_failures} 次工具调用失败，已终止。"
                    "请调整工具选择或参数。"
                ) from exc

            return f"ERROR: {error_text}"

    @staticmethod
    def _build_call_signature(tool_name: str, tool_params: dict[str, Any]) -> str:
        try:
            payload = json.dumps(tool_params, sort_keys=True, ensure_ascii=True)
        except TypeError:
            payload = repr(tool_params)
        return f"{tool_name}:{payload}"

    def _get_tool_schema_hint(self, tool_name: str) -> str | None:
        try:
            tool = self.tool_registry.get(tool_name)
            return json.dumps(tool.params_model.model_json_schema(), ensure_ascii=True)
        except Exception:
            return None

    @staticmethod
    def _parse_json_response(response: str) -> dict[str, Any]:
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9]*", "", text).strip()
            text = re.sub(r"```$", "", text).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise AgentException("模型未返回合法 JSON 对象。")

        snippet = text[start:end + 1]
        try:
            payload = json.loads(snippet)
        except json.JSONDecodeError as exc:
            raise AgentException(f"JSON 解析失败: {exc}") from exc

        if not isinstance(payload, dict):
            raise AgentException("响应必须是 JSON 对象。")

        response_type = payload.get("type")
        if response_type not in {"action", "final"}:
            raise AgentException("JSON 响应必须包含 type=action 或 type=final。")

        if response_type == "final":
            if "final" not in payload:
                raise AgentException("type=final 时必须提供 final 字段。")
            return {"type": "final", "final": str(payload["final"])}

        action = payload.get("action")
        if not isinstance(action, dict):
            raise AgentException("type=action 时必须提供 action 对象。")
        return {"type": "action", "action": action}

    @staticmethod
    def _normalize_input(input_text: str) -> str:
        text = input_text.strip() if isinstance(input_text, str) else ""
        if not text:
            raise AgentException("input_text 不能为空")
        return text

