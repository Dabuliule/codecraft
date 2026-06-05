from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from typing import TYPE_CHECKING

from codecraft.core.turn_context import TurnContext
from codecraft.llm.events import ModelEventType
from codecraft.schema.event import RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.tool import ToolCall, ToolResult

if TYPE_CHECKING:
    from codecraft.core.session import Session


class TurnStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    WAITING_APPROVAL = "waiting_approval"
    FINISHED = "finished"
    ABORTED = "aborted"
    FAILED = "failed"


class Turn:
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
        self.step_count = 0
        self.cancel_requested = False

    async def run(self, user_input: SessionInput) -> None:
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
            if self.step_count >= self.context.max_steps:
                await self._abort("max_steps_exceeded", "Turn exceeded max tool/model steps.")
                return

            tool_was_called = False
            assistant_parts: list[str] = []
            completed_message: str | None = None

            async for model_event in self.session.llm_provider.stream(
                self.session.conversation.build_model_messages(),
                self.context.available_tools,
                self.context,
            ):
                if self.cancel_requested:
                    await self._abort("user_interrupt", "Turn interrupted by user.")
                    return

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
                    self.session.conversation.append_assistant_message(completed_message)

                elif model_event.type == ModelEventType.TOKEN_COUNT:
                    await self.session.emit(
                        RuntimeEventType.TOKEN_COUNT,
                        dict(model_event.payload),
                        turn_id=self.turn_id,
                    )

                elif model_event.type == ModelEventType.TOOL_CALL:
                    tool_was_called = True
                    await self._run_tool_call(model_event.payload)
                    break

                elif model_event.type == ModelEventType.ERROR:
                    await self.session.emit(
                        RuntimeEventType.ERROR,
                        dict(model_event.payload),
                        turn_id=self.turn_id,
                    )
                    await self._abort("model_error", str(model_event.payload.get("message", "")))
                    return

                elif model_event.type == ModelEventType.COMPLETED:
                    break

            if tool_was_called:
                self.step_count += 1
                continue

            if completed_message is None:
                completed_message = "".join(assistant_parts)
                if completed_message:
                    await self.session.emit(
                        RuntimeEventType.ASSISTANT_MESSAGE,
                        {"text": completed_message},
                        turn_id=self.turn_id,
                    )
                    self.session.conversation.append_assistant_message(completed_message)

            answer = completed_message or ""
            break

        self.status = TurnStatus.FINISHED
        await self.session.emit(
            RuntimeEventType.TURN_FINISHED,
            {
                "status": "success",
                "answer": answer or "",
                "steps": self.step_count,
                "duration_ms": int((monotonic() - started_at) * 1000),
            },
            turn_id=self.turn_id,
        )

    async def _run_tool_call(self, payload: dict) -> ToolResult:
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
            thread_id=config.thread_id,
            turn_id=self.turn_id,
            cwd=config.cwd,
            workspace_roots=config.workspace_roots,
            model=config.model,
            model_provider=config.model_provider,
            approval_policy=config.approval_policy,
            sandbox_mode=config.sandbox_mode,
            network_access=config.network_access,
            available_tools=self.session.tool_registry.specs(),
            max_steps=config.max_turn_steps,
            max_tool_output_chars=config.max_tool_output_chars,
            created_at=datetime.now(UTC),
        )

    async def _abort(self, reason: str, message: str) -> None:
        self.status = TurnStatus.ABORTED
        await self.session.emit(
            RuntimeEventType.TURN_ABORTED,
            {
                "reason": reason,
                "message": message,
                "steps": self.step_count,
            },
            turn_id=self.turn_id,
        )
