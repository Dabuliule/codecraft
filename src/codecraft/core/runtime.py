from __future__ import annotations

import asyncio
from dataclasses import dataclass

from codecraft.core.approval_gate import ApprovalGate, ApprovalGateRequest
from codecraft.core.agent import Agent
from codecraft.core.event_bus import EventBus
from codecraft.schema.approval import ApprovalDecision, ApprovalRequest
from codecraft.schema.event import (
    ApprovalRequestEvent,
    FinalResultEvent,
    ObservationEvent,
    RuntimeEvent,
    ThoughtEvent,
    ToolCallEvent,
)
from codecraft.schema.result import AgentResult
from codecraft.schema.state import AgentState
from codecraft.schema.step import Step
from codecraft.schema.strategy import Strategy


@dataclass(frozen=True)
class PendingApproval:
    request: ApprovalRequest
    event: ApprovalRequestEvent
    decision: asyncio.Future[ApprovalDecision]


class AgentRuntime:
    """
    Step-Based Agent Runtime。

    Runtime 是唯一 orchestration owner。

    职责：
    - 驱动 step loop
    - 管理 state
    - 控制 execution lifecycle
    - 保持 runtime grounded
    """

    def __init__(
            self,
            agent: Agent,
            approval_gate: ApprovalGate,
            event_bus: EventBus | None = None,
            max_steps: int = 50,
    ) -> None:

        self.agent = agent
        self.approval_gate = approval_gate
        self.event_bus = event_bus or EventBus()

        self.max_steps = max_steps
        self.current_state: AgentState | None = None
        self.pending_approvals: dict[str, PendingApproval] = {}

    async def _emit(
            self,
            event: RuntimeEvent,
    ) -> RuntimeEvent:
        if self.current_state and event.trace_id is None:
            event.trace_id = self.current_state.trace_id

        await self.event_bus.emit(event)
        return event

    async def astream(
            self,
            task: str,
    ):

        state = AgentState(
            task=task,
            strategy=Strategy(
                objective=task,
                current_focus="理解任务",
                approach="逐步观察并执行",
            ),
        )
        self.current_state = state

        step_count = 0

        while not state.done:

            if step_count >= self.max_steps:
                raise RuntimeError(
                    "Agent 超过最大执行步数"
                )

            decision = await self.agent.astep(
                state=state
            )

            state.current_decision = decision

            yield await self._emit(
                ThoughtEvent(
                    thought=decision.rationale,
                )
            )

            tool_call = decision.tool_call

            yield await self._emit(
                ToolCallEvent(
                    tool=tool_call.tool,
                    args=tool_call.args,
                )
            )

            step_id = f"step-{step_count + 1}"
            approval_request = self.approval_gate.build_request(
                ApprovalGateRequest(
                    step_id=step_id,
                    tool_call=tool_call,
                )
            )

            if approval_request is None:
                outcome = await self.approval_gate.run_tool(
                    tool_call=tool_call,
                    emit=self._emit,
                )

                for event in outcome.events:
                    yield event

            else:
                request_event = self.approval_gate.build_request_event(
                    approval_request
                )
                pending = self._create_pending_approval(
                    approval_request=approval_request,
                    request_event=request_event,
                )

                yield await self._emit(request_event)

                try:
                    approval_decision = await pending.decision
                finally:
                    self.pending_approvals.pop(
                        approval_request.approval_id,
                        None,
                    )

                yield await self._emit(
                    self.approval_gate.build_decision_event(
                        approval_request,
                        approval_decision,
                    )
                )

                outcome = await self.approval_gate.apply_decision(
                    approval_request=approval_request,
                    decision=approval_decision,
                    emit=self._emit,
                )

                for event in outcome.events:
                    yield event

            tool_result = outcome.execution.result
            executed_tool_call = outcome.tool_call

            yield await self._emit(
                ObservationEvent(
                    content=str(tool_result.content),
                    success=tool_result.success,
                    data=tool_result.data,
                    error=tool_result.error,
                    suggestion=tool_result.suggestion,
                )
            )

            step = Step(
                step_id=step_id,
                thought=decision.rationale,
                tool_call=executed_tool_call,
                observation=tool_result,
                success=tool_result.success,
                summary=self._build_step_summary(
                    tool_call=executed_tool_call,
                    tool_result=tool_result,
                ),
            )

            state.recent_steps.append(step)

            self._maybe_compress_memory(
                state
            )

            self._detect_warnings(
                state,
                step,
            )

            if executed_tool_call.tool == "final_answer":
                state.done = True

                state.final_answer = (
                    tool_result.content
                )

                result = AgentResult(
                    success=True,
                    answer=state.final_answer,
                    steps=state.recent_steps,
                    memory=state.memory,
                    warnings=state.warnings,
                    total_steps=len(
                        state.recent_steps
                    ),
                )

                yield await self._emit(
                    FinalResultEvent(
                        result=result,
                    )
                )

                return

            step_count += 1

    def decide_approval(
            self,
            approval_id: str,
            decision: ApprovalDecision,
    ) -> None:
        pending = self.pending_approvals.get(approval_id)
        if pending is None:
            raise KeyError(f"Unknown pending approval: {approval_id}")

        if pending.decision.done():
            raise RuntimeError(f"Approval already decided: {approval_id}")

        pending.decision.set_result(decision)

    def list_pending_approvals(self) -> tuple[ApprovalRequestEvent, ...]:
        return tuple(
            pending.event
            for pending in self.pending_approvals.values()
        )

    def _create_pending_approval(
            self,
            *,
            approval_request: ApprovalRequest,
            request_event: ApprovalRequestEvent,
    ) -> PendingApproval:
        if approval_request.approval_id in self.pending_approvals:
            raise RuntimeError(
                f"Duplicate pending approval: {approval_request.approval_id}"
            )

        pending = PendingApproval(
            request=approval_request,
            event=request_event,
            decision=asyncio.get_running_loop().create_future(),
        )
        self.pending_approvals[approval_request.approval_id] = pending
        return pending

    async def arun(
            self,
            task: str,
    ) -> AgentResult:

        final_result = None

        async for event in self.astream(
                task=task,
        ):
            if isinstance(event, FinalResultEvent):
                final_result = event.result

        if final_result is None:
            raise RuntimeError("Runtime 未产生最终结果")

        return final_result

    @staticmethod
    def _build_step_summary(
            tool_call,
            tool_result,
    ) -> str:

        if getattr(tool_result, "error", None):
            return (
                f"{tool_call.tool} 执行失败："
                f"{tool_result.error}"
            )

        content = getattr(
            tool_result,
            "content",
            "",
        )

        short_content = str(content)[:120]

        return (
            f"{tool_call.tool} 执行成功："
            f"{short_content}"
        )

    @staticmethod
    def _maybe_compress_memory(
            state: AgentState,
    ) -> None:
        if len(state.recent_steps) <= 8:
            return

        old_step = state.recent_steps.pop(0)

        state.memory.append(
            old_step.summary
        )

    @staticmethod
    def _detect_warnings(
            state: AgentState,
            step: Step,
    ) -> None:
        if not step.success:
            state.warnings.append(f"{step.tool_call.tool} 执行失败")

        # 防止 warning 无限增长
        state.warnings = state.warnings[-10:]
