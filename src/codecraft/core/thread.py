from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from codecraft.core.session import Session, SessionStatus
from codecraft.approval.manager import ApprovalRequest
from codecraft.approval.thread_reviewer import ThreadApprovalReviewer
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.session import SessionSnapshot


class AgentThread:
    """面向 CLI/UI 的 session facade。

    `AgentThread` 把 Session 的事件总线转成一个异步队列，让调用方可以像读
    stream 一样消费事件，同时隐藏 session 的调度细节。
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self._events: asyncio.Queue[RuntimeEvent] = asyncio.Queue()
        self.session.event_bus.subscribe(self._capture_event)

    async def submit(self, input: SessionInput) -> str:
        return await self.session.submit(input)

    async def next_event(self) -> RuntimeEvent:
        return await self._events.get()

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        """持续产出事件，直到收到 SESSION_CLOSED。"""
        while True:
            event = await self.next_event()
            yield event
            if event.type == RuntimeEventType.SESSION_CLOSED:
                return

    async def interrupt(self, reason: str = "user_interrupt") -> None:
        await self.session.interrupt(reason)

    async def close(self) -> None:
        await self.session.close()

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        """返回当前等待用户处理的审批请求。"""
        reviewer = self.session.approval_manager.reviewer
        if isinstance(reviewer, ThreadApprovalReviewer):
            return reviewer.list_pending()
        return []

    async def read_snapshot(self) -> SessionSnapshot:
        events = await self.session.session_store.load_events(self.session.session_id)
        return SessionSnapshot(config=self.session.config, events=events)

    async def wait_until_idle(self) -> None:
        """等待当前后台 turn 结束。

        测试和命令行一次性执行会用它确保事件都写完后再退出。
        """
        task = self.session._runner_task
        if task is not None:
            await task
        while self.session.status == SessionStatus.RUNNING:
            await asyncio.sleep(0)

    async def _capture_event(self, event: RuntimeEvent) -> None:
        await self._events.put(event)
