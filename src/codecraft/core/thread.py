from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from codecraft.core.session import Session, SessionStatus
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.session import SessionSnapshot


class AgentThread:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._events: asyncio.Queue[RuntimeEvent] = asyncio.Queue()
        self.session.event_bus.subscribe(self._capture_event)

    async def submit(self, input: SessionInput) -> str:
        return await self.session.submit(input)

    async def next_event(self) -> RuntimeEvent:
        return await self._events.get()

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        while True:
            event = await self.next_event()
            yield event
            if event.type == RuntimeEventType.SESSION_CLOSED:
                return

    async def interrupt(self, reason: str = "user_interrupt") -> None:
        await self.session.interrupt(reason)

    async def close(self) -> None:
        await self.session.close()

    async def read_snapshot(self) -> SessionSnapshot:
        events = await self.session.session_store.load_events(self.session.session_id)
        return SessionSnapshot(config=self.session.config, events=events)

    async def wait_until_idle(self) -> None:
        task = self.session._runner_task
        if task is not None:
            await task
        while self.session.status == SessionStatus.RUNNING:
            await asyncio.sleep(0)

    async def _capture_event(self, event: RuntimeEvent) -> None:
        await self._events.put(event)
