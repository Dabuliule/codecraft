from __future__ import annotations

from agent_runtime.core.agent import Agent
from agent_runtime.core.event_bus import EventBus
from agent_runtime.core.executor import Executor
from agent_runtime.observability.context import trace_scope
from agent_runtime.schema.event import (
    FinalResultEvent,
    IntentRequestEvent,
    ObservationEvent,
    OperationEvent,
    RuntimeEvent,
    ThoughtEvent,
)
from agent_runtime.schema.result import AgentResult
from agent_runtime.schema.state import AgentState
from agent_runtime.schema.step import Step
from agent_runtime.schema.strategy import Strategy


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
            executor: Executor,
            event_bus: EventBus | None = None,
            max_steps: int = 50,
    ) -> None:

        self.agent = agent
        self.executor = executor
        self.event_bus = event_bus or EventBus()

        self.max_steps = max_steps

    async def _emit(
            self,
            event: RuntimeEvent,
    ) -> RuntimeEvent:
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

        with trace_scope(
                trace_id=state.trace_id,
                component="runtime",
        ):

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
                        thought=decision.thought,
                    )
                )

                if not decision.plan.intents:
                    raise RuntimeError("Agent 返回了空 IntentPlan")

                for intent in decision.plan.intents:
                    yield await self._emit(
                        IntentRequestEvent(
                            intent=intent.intent,
                            target=intent.target,
                            params=intent.params,
                        )
                    )

                    execution = await self.executor.execute(
                        intent,
                    )

                    operation_name = (
                        execution.resolved.operation.name
                        if execution.resolved
                        else "<unresolved>"
                    )
                    tool_input = (
                        execution.resolved.args
                        if execution.resolved
                        else {}
                    )

                    yield await self._emit(
                        OperationEvent(
                            operation=operation_name,
                            intent=intent.intent,
                            tool_input=tool_input,
                        )
                    )

                    operation_result = execution.result

                    yield await self._emit(
                        ObservationEvent(
                            content=str(operation_result.content),
                            success=operation_result.success,
                            error=operation_result.error,
                            suggestion=operation_result.suggestion,
                        )
                    )

                    step = Step(
                        step_id=f"step-{step_count + 1}",
                        thought=decision.thought,
                        intent=intent,
                        operation=operation_name,
                        observation=operation_result,
                        success=operation_result.success,
                        summary=self._build_step_summary(
                            intent=intent,
                            operation=operation_name,
                            operation_result=operation_result,
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

                    if intent.intent == "response.final":
                        state.done = True

                        state.final_answer = (
                            operation_result.content
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

                    if step_count >= self.max_steps:
                        raise RuntimeError(
                            "Agent 超过最大执行步数"
                        )

                    if not operation_result.success:
                        break

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
            intent,
            operation,
            operation_result,
    ) -> str:

        if getattr(operation_result, "error", None):
            return (
                f"{intent.intent} -> {operation} 执行失败："
                f"{operation_result.error}"
            )

        content = getattr(
            operation_result,
            "content",
            "",
        )

        short_content = str(content)[:120]

        return (
            f"{intent.intent} -> {operation} 执行成功："
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
            state.warnings.append(f"{step.intent.intent} 执行失败")

        # 防止 warning 无限增长
        state.warnings = state.warnings[-10:]
