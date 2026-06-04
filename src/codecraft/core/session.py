from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Any

from codecraft.core.conversation import Conversation
from codecraft.core.event_bus import EventBus
from codecraft.core.ids import new_id
from codecraft.core.input_queue import InputQueue
from codecraft.core.session_store import SessionStore
from codecraft.core.turn import Turn
from codecraft.llm.base import LLMProvider
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput, SessionInputType
from codecraft.schema.session import SessionConfig
from codecraft.tool.registry import ToolRegistry


class SessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    CLOSED = "closed"


class Session:
    def __init__(
        self,
        *,
        config: SessionConfig,
        session_store: SessionStore,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        event_bus: EventBus | None = None,
        conversation: Conversation | None = None,
        seq: int = 0,
    ) -> None:
        self.session_id = config.session_id
        self.thread_id = config.thread_id
        self.config = config
        self.conversation = conversation or Conversation()
        self.input_queue = InputQueue()
        self.active_turn: Turn | None = None
        self.status = SessionStatus.IDLE
        self.event_bus = event_bus or EventBus()
        self.session_store = session_store
        self.seq = seq
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self._emit_lock = asyncio.Lock()
        self._runner_task: asyncio.Task[None] | None = None

    async def submit(self, input: SessionInput) -> str:
        if self.status == SessionStatus.CLOSED:
            raise RuntimeError("session is closed")

        if input.type == SessionInputType.USER_MESSAGE:
            await self.input_queue.put(input)
            await self.start_turn_if_idle()
            return input.input_id

        if input.type == SessionInputType.INTERRUPT:
            await self.interrupt(str(input.payload.get("reason", "user_interrupt")))
            return input.input_id

        await self.input_queue.put(input)
        return input.input_id

    async def start_turn_if_idle(self) -> None:
        if self.status != SessionStatus.IDLE:
            return
        if self.input_queue.empty():
            return

        user_input = await self.input_queue.get()
        turn = Turn(
            session=self,
            turn_id=new_id("turn_"),
        )
        self.active_turn = turn
        self.status = SessionStatus.RUNNING
        self._runner_task = asyncio.create_task(self._run_turn(turn, user_input))

    async def emit(
        self,
        event_type: RuntimeEventType,
        payload: dict[str, Any] | None = None,
        turn_id: str | None = None,
    ) -> RuntimeEvent:
        async with self._emit_lock:
            self.seq += 1
            event = RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=self.session_id,
                turn_id=turn_id,
                seq=self.seq,
                type=event_type,
                payload=payload or {},
            )
            await self.session_store.append_event(event)
            await self.event_bus.emit(event)
            return event

    async def interrupt(self, reason: str) -> None:
        if self.active_turn is not None:
            self.active_turn.cancel_requested = True
            await self.emit(
                RuntimeEventType.TURN_ABORTED,
                {"reason": reason, "message": reason},
                turn_id=self.active_turn.turn_id,
            )
        self.status = SessionStatus.INTERRUPTED
        self.status = SessionStatus.IDLE

    async def close(self) -> None:
        if self.status == SessionStatus.CLOSED:
            return
        await self.emit(RuntimeEventType.SESSION_CLOSED)
        self.status = SessionStatus.CLOSED

    async def _run_turn(self, turn: Turn, user_input: SessionInput) -> None:
        try:
            await turn.run(user_input)
        except Exception as exc:
            self.status = SessionStatus.FAILED
            await self.emit(
                RuntimeEventType.ERROR,
                {
                    "code": "runtime_error",
                    "message": str(exc),
                },
                turn_id=turn.turn_id,
            )
            await self.emit(
                RuntimeEventType.TURN_ABORTED,
                {
                    "reason": "runtime_error",
                    "message": str(exc),
                    "steps": turn.step_count,
                },
                turn_id=turn.turn_id,
            )
        finally:
            if self.status != SessionStatus.CLOSED:
                self.active_turn = None
                if self.status != SessionStatus.FAILED:
                    self.status = SessionStatus.IDLE
                await self.start_turn_if_idle()
