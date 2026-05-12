from __future__ import annotations

from typing import Optional

from core.executor import Executor
from core.planner import Planner
from observability.context import trace_scope
from schema.action import Action
from schema.state import AgentState


class AgentRuntime:
    """Planner-driven agent runtime."""

    def __init__(self, planner: Planner, executor: Executor) -> None:
        self.planner = planner
        self.executor = executor

    async def arun(self, task: str, *, max_steps: Optional[int] = None) -> AgentState:
        state = AgentState(task=task)

        if max_steps is not None:
            state.max_steps = max_steps

        with trace_scope(trace_id=state.trace_id, component="runtime"):
            while not state.done and state.current_step < state.max_steps:
                with trace_scope(step=state.current_step, component="planner"):
                    planned_steps = await self.planner.aplan(state)

                if not planned_steps:
                    state.done = True
                    break

                for planned_step in planned_steps:
                    if state.current_step >= state.max_steps:
                        state.done = True
                        break

                    with trace_scope(step=state.current_step, component="executor"):
                        action = Action(
                            type="tool",
                            tool=planned_step.tool,
                            tool_input=planned_step.tool_input,
                            final_answer=None
                        )
                        executed_step = await self.executor.execute(action)

                    state.history.append(executed_step)
                    state.current_step += 1

            return state
