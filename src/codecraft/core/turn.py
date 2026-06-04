from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from typing import TYPE_CHECKING

from codecraft.core.turn_context import TurnContext
from codecraft.llm.events import ModelEventType
from codecraft.schema.event import RuntimeEventType
from codecraft.schema.input import SessionInput

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
                await self._abort(
                    "tool_calls_not_supported",
                    "Tool calls are not implemented in this phase.",
                )
                return

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

        answer = completed_message
        if answer is None:
            answer = "".join(assistant_parts)
            if answer:
                await self.session.emit(
                    RuntimeEventType.ASSISTANT_MESSAGE,
                    {"text": answer},
                    turn_id=self.turn_id,
                )
                self.session.conversation.append_assistant_message(answer)

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
