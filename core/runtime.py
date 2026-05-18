from __future__ import annotations

from core.agent import Agent
from core.executor import Executor
from observability.context import trace_scope
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

    async def arun(
            self,
            task: str,
    ) -> AgentResult:

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
                    state=state,
                )

                state.current_decision = decision

                print("\n🧠 Thought")
                print(decision.thought)

                print("\n🎯 Action")
                print(decision.action.pretty())

                tool_result = await self.executor.execute(
                    decision.action,
                )

                step = Step(
                    step_id=f"step-{step_count + 1}",
                    thought=decision.thought,
                    action=decision.action,
                    observation=tool_result,
                    success=not bool(tool_result.error),
                    summary=self._build_step_summary(
                        decision=decision,
                        tool_result=tool_result,
                    ),
                )

                state.recent_steps.append(step)

                self._maybe_compress_memory(state)

                if decision.is_terminal:
                    state.done = True

                    if hasattr(tool_result, "content"):
                        state.final_answer = tool_result.content
                    else:
                        state.final_answer = str(tool_result)

                    break

                self._detect_warnings(
                    state=state,
                    step=step,
                )

                step_count += 1

            return AgentResult(
                success=state.done,
                answer=state.final_answer,
                steps=state.recent_steps,
            )

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
