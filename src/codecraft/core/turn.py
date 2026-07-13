from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from typing import TYPE_CHECKING

from codecraft.core.turn_context import TurnContext
from codecraft.llm.events import ModelEventType
from codecraft.prompt import PromptBuilder
from codecraft.schema.event import RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.tool import ToolCall, ToolResult

if TYPE_CHECKING:
    from codecraft.core.session import Session


class TurnStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    FINISHED = "finished"
    ABORTED = "aborted"


class Turn:
    """一次用户输入对应的模型执行轮次。

    `Turn` 管理从用户消息进入对话、调用模型、执行 tool call，到产出最终
    assistant 消息的完整循环。它不负责持久化细节，所有外部可见状态都通过
    session event 发出去。
    """

    def __init__(
        self,
        *,
        session: Session,
        turn_id: str,
    ) -> None:
        self.turn_id = turn_id
        self.session = session
        self.context = self._build_context()
        self.status = TurnStatus.CREATED
        self.tool_call_count = 0
        self.prompt_builder = PromptBuilder()

    async def run(self, user_input: SessionInput) -> None:
        """运行一次用户输入，直到模型给出最终回复或轮次中止。

        模型可能在一次响应中要求调用工具；工具结果会回填到 conversation，
        然后继续下一次模型调用，直到没有新的 tool call。
        """
        started_at = monotonic()
        self.status = TurnStatus.RUNNING
        text = str(user_input.payload.get("text", ""))
        await self.session.emit(
            RuntimeEventType.TURN_STARTED,
            {"input_id": user_input.input_id},
            turn_id=self.turn_id,
        )
        await self.session.emit(
            RuntimeEventType.USER_MESSAGE,
            {"input_id": user_input.input_id, "text": text},
            turn_id=self.turn_id,
        )
        self.session.conversation.append_user_message(text)

        answer = ""

        while True:
            tool_calls: list[dict] = []
            assistant_parts: list[str] = []
            completed_message: str | None = None

            async for model_event in self.session.llm_provider.stream(
                self.prompt_builder.build(
                    config=self.session.config,
                    conversation=self.session.conversation,
                    context=self.context,
                ),
                self.context.available_tools,
                self.context,
            ):
                if model_event.type == ModelEventType.MESSAGE_DELTA:
                    delta = str(model_event.payload.get("text", ""))
                    assistant_parts.append(delta)
                    await self.session.emit(
                        RuntimeEventType.ASSISTANT_MESSAGE_DELTA,
                        {"text": delta},
                        turn_id=self.turn_id,
                    )

                elif model_event.type == ModelEventType.MESSAGE_COMPLETED:
                    completed_message = str(model_event.payload.get("text", ""))
                    await self.session.emit(
                        RuntimeEventType.ASSISTANT_MESSAGE,
                        {"text": completed_message},
                        turn_id=self.turn_id,
                    )
                    self.session.conversation.append_assistant_message(
                        completed_message
                    )

                elif model_event.type == ModelEventType.TOKEN_COUNT:
                    await self.session.emit(
                        RuntimeEventType.TOKEN_COUNT,
                        dict(model_event.payload),
                        turn_id=self.turn_id,
                    )

                elif model_event.type == ModelEventType.TOOL_CALL:
                    tool_calls.append(dict(model_event.payload))

                elif model_event.type == ModelEventType.ERROR:
                    await self.session.emit(
                        RuntimeEventType.ERROR,
                        dict(model_event.payload),
                        turn_id=self.turn_id,
                    )
                    await self.abort(
                        "model_error", str(model_event.payload.get("message", ""))
                    )
                    return

                elif model_event.type == ModelEventType.COMPLETED:
                    break

            if tool_calls:
                completed_message = await self._flush_streamed_message(
                    assistant_parts,
                    completed_message,
                )
                if self.tool_call_count + len(tool_calls) > self.context.max_tool_calls:
                    await self.abort(
                        "max_tool_calls_exceeded",
                        "Turn requested more tool calls than the configured limit.",
                    )
                    return
                for payload in tool_calls:
                    await self._run_tool_call(payload)
                    self.tool_call_count += 1
                continue

            if completed_message is None:
                completed_message = "".join(assistant_parts)
                if completed_message:
                    await self.session.emit(
                        RuntimeEventType.ASSISTANT_MESSAGE,
                        {"text": completed_message},
                        turn_id=self.turn_id,
                    )
                    self.session.conversation.append_assistant_message(
                        completed_message
                    )

            answer = completed_message or ""
            break

        self.status = TurnStatus.FINISHED
        await self.session.emit(
            RuntimeEventType.TURN_FINISHED,
            {
                "status": "success",
                "answer": answer or "",
                "tool_calls": self.tool_call_count,
                "duration_ms": int((monotonic() - started_at) * 1000),
            },
            turn_id=self.turn_id,
        )

    async def _flush_streamed_message(
        self,
        assistant_parts: list[str],
        completed_message: str | None,
    ) -> str | None:
        if completed_message is not None:
            return completed_message

        streamed_message = "".join(assistant_parts)
        if not streamed_message:
            return None

        await self.session.emit(
            RuntimeEventType.ASSISTANT_MESSAGE,
            {"text": streamed_message},
            turn_id=self.turn_id,
        )
        self.session.conversation.append_assistant_message(streamed_message)
        return streamed_message

    async def _run_tool_call(self, payload: dict) -> ToolResult:
        """执行模型发起的 tool call，并把调用和结果写回 conversation。"""
        call = self._build_tool_call(payload)
        await self.session.emit(
            RuntimeEventType.MODEL_TOOL_CALL,
            call.model_dump(mode="json"),
            turn_id=self.turn_id,
        )
        self.session.conversation.append_model_tool_call(
            call.call_id,
            call.name,
            call.arguments,
        )

        result: ToolResult | None = None
        async for runner_event in self.session.tool_runner.run(call, self.context):
            await self.session.emit(
                runner_event.type,
                runner_event.payload,
                turn_id=self.turn_id,
            )
            if runner_event.type == RuntimeEventType.TOOL_CALL_FINISHED:
                result = ToolResult.model_validate(runner_event.payload["result"])

        if result is None:
            result = ToolResult(
                success=False,
                content="Tool did not produce a result.",
                error="tool_result_missing",
            )

        self.session.conversation.append_tool_result(
            call.call_id,
            call.name,
            result.content,
        )
        return result

    @staticmethod
    def _build_tool_call(payload: dict) -> ToolCall:
        """兼容不同 provider 的 tool call 字段命名。"""
        if "call_id" in payload and "name" in payload:
            return ToolCall.model_validate(payload)

        return ToolCall(
            call_id=str(payload.get("call_id", "")) or "call_auto",
            name=str(payload.get("name") or payload.get("tool")),
            arguments=dict(payload.get("arguments") or payload.get("args") or {}),
        )

    def _build_context(self) -> TurnContext:
        config = self.session.config
        return TurnContext(
            session_id=config.session_id,
            turn_id=self.turn_id,
            cwd=config.cwd,
            workspace_roots=config.workspace_roots,
            model=config.model,
            model_provider=config.model_provider,
            approval_policy=config.approval_policy,
            sandbox_mode=config.sandbox_mode,
            network_access=config.network_access,
            sandbox_env_allowlist=config.sandbox_env_allowlist,
            available_tools=self.session.tool_registry.specs(),
            max_tool_calls=config.max_tool_calls,
            max_tool_output_chars=config.max_tool_output_chars,
            created_at=datetime.now(UTC),
        )

    async def abort(self, reason: str, message: str) -> None:
        self.status = TurnStatus.ABORTED
        await self.session.emit(
            RuntimeEventType.TURN_ABORTED,
            {
                "reason": reason,
                "message": message,
                "tool_calls": self.tool_call_count,
            },
            turn_id=self.turn_id,
        )
