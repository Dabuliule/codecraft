from __future__ import annotations

from core.agent import Agent
from core.executor import Executor
from observability.context import trace_scope
from schema.event import ActionEvent, FinalResultEvent, ObservationEvent, ThoughtEvent
from schema.result import AgentResult
from schema.state import AgentState
from schema.step import Step
from schema.strategy import Strategy


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
            max_steps: int = 50,
    ) -> None:

        self.agent = agent
        self.executor = executor

        self.max_steps = max_steps

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

                yield ThoughtEvent(
                    thought=decision.thought,
                )

                yield ActionEvent(
                    tool=decision.action.tool,
                    tool_input=decision.action.tool_input,
                )

                tool_result = await self.executor.execute(
                    decision.action,
                )

                yield ObservationEvent(
                    content=str(tool_result.content),
                    success=tool_result.success,
                )

                step = Step(
                    step_id=f"step-{step_count + 1}",
                    thought=decision.thought,
                    action=decision.action,
                    observation=tool_result,
                    success=tool_result.success,
                    summary=self._build_step_summary(
                        decision=decision,
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

                if decision.is_terminal:
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

                    yield FinalResultEvent(
                        result=result,
                    )

                    return

                step_count += 1

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
            decision,
            tool_result,
    ) -> str:

        tool_name = decision.action.tool

        if getattr(tool_result, "error", None):
            return (
                f"{tool_name} 执行失败："
                f"{tool_result.error}"
            )

        content = getattr(
            tool_result,
            "content",
            "",
        )

        short_content = str(content)[:120]

        return (
            f"{tool_name} 执行成功："
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
            state.warnings.append(f"{step.action.tool} 执行失败")

        # 防止 warning 无限增长
        state.warnings = state.warnings[-10:]
