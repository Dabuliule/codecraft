from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Any

from codecraft.approval.manager import ApprovalDecision, ApprovalManager
from codecraft.approval.thread_reviewer import ThreadApprovalReviewer
from codecraft.core.errors import CodecraftError
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
from codecraft.tool.runner import ToolRunner


class SessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    CLOSED = "closed"


class Session:
    """一个可持续追加事件的 agent 会话。

    `Session` 是运行时的调度中心：接收输入、串行启动 turn、分发审批决定，
    并把所有关键状态写成 RuntimeEvent。外层 UI 不直接读取内部状态，而是
    通过 event stream 观察会话变化。
    """

    def __init__(
        self,
        *,
        config: SessionConfig,
        session_store: SessionStore,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        approval_manager: ApprovalManager | None = None,
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
        self.approval_reviewer = ThreadApprovalReviewer()
        self.approval_manager = approval_manager or ApprovalManager(
            reviewer=self.approval_reviewer
        )
        self.tool_runner = ToolRunner(
            tool_registry, approval_manager=self.approval_manager
        )
        self._emit_lock = asyncio.Lock()
        self._runner_task: asyncio.Task[None] | None = None

    async def submit(self, input: SessionInput) -> str:
        """提交用户输入、审批结果或中断请求。"""
        if self.status == SessionStatus.CLOSED:
            raise RuntimeError("session is closed")

        if input.type == SessionInputType.USER_MESSAGE:
            await self.input_queue.put(input)
            await self.start_turn_if_idle()
            return input.input_id

        if input.type == SessionInputType.INTERRUPT:
            await self.interrupt(str(input.payload.get("reason", "user_interrupt")))
            return input.input_id

        if input.type == SessionInputType.APPROVAL_DECISION:
            self.submit_approval_decision(input)
            return input.input_id

        await self.input_queue.put(input)
        return input.input_id

    def submit_approval_decision(self, input: SessionInput) -> None:
        """把用户审批结果交给正在等待的 reviewer。"""
        decision = ApprovalDecision(
            approval_id=str(input.payload["approval_id"]),
            approved=bool(input.payload["approved"]),
            reviewer="user",
            reason=input.payload.get("reason"),
        )
        reviewer = self.approval_manager.reviewer
        if not isinstance(reviewer, ThreadApprovalReviewer):
            raise RuntimeError(
                "current approval reviewer does not accept thread decisions"
            )
        reviewer.decide(decision)

    async def start_turn_if_idle(self) -> None:
        """如果当前空闲，就从输入队列取一条消息启动新 turn。"""
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
        """持久化并广播一个 RuntimeEvent。

        seq 是 session 日志的顺序号；写入失败时回滚 seq，避免后续事件出现
        不连续的编号。
        """
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
            try:
                await self.session_store.append_event(event)
            except Exception:
                self.seq -= 1
                raise
            await self.event_bus.emit(event)
            return event

    async def interrupt(self, reason: str) -> None:
        """请求当前 turn 尽快停止，并让 session 回到可接收输入的状态。"""
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
        if self.active_turn is not None:
            self.active_turn.cancel_requested = True
        await self.emit(RuntimeEventType.SESSION_CLOSED)
        self.status = SessionStatus.CLOSED

    async def _run_turn(self, turn: Turn, user_input: SessionInput) -> None:
        """包装 turn.run，确保异常也会变成可追踪的事件。"""
        try:
            await turn.run(user_input)
        except Exception as exc:
            self.status = SessionStatus.FAILED
            error_payload = self._error_payload(exc)
            await self.emit(
                RuntimeEventType.ERROR,
                error_payload,
                turn_id=turn.turn_id,
            )
            await self.emit(
                RuntimeEventType.TURN_ABORTED,
                {
                    "reason": error_payload["code"],
                    "message": error_payload["message"],
                    "metadata": error_payload.get("metadata", {}),
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

    @staticmethod
    def _error_payload(exc: Exception) -> dict[str, Any]:
        if isinstance(exc, CodecraftError):
            return {
                "code": exc.code,
                "message": exc.message,
                "metadata": exc.metadata,
                "suggestion": exc.suggestion,
            }
        return {
            "code": "runtime_error",
            "message": str(exc),
            "metadata": {},
            "suggestion": None,
        }
