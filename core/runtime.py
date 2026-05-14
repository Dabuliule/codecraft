from __future__ import annotations

from core.executor import Executor
from core.planner import Planner
from core.reflector import Reflector
from observability.context import trace_scope
from schema.state import AgentState


class AgentRuntime:
    """
    Planner → Executor → Reflector 驱动的 Agent Runtime。
    只负责 orchestration（编排）。
    """

    def __init__(self, planner: Planner, executor: Executor, reflector: Reflector) -> None:
        self.planner = planner
        self.executor = executor
        self.reflector = reflector

    async def arun(self, task: str) -> AgentState:
        state = AgentState(task=task)

        with trace_scope(trace_id=state.trace_id, component="runtime"):
            while not state.done:
                plan = await self.planner.aplan(state)

                if not plan.actions:
                    state.done = True
                    break

                for action in plan.actions:
                    step = await self.executor.execute(action)
                    state.history.append(step)
                    reflection = await self.reflector.areflect(state)

                    match reflection.status:
                        case "success":
                            state.done = True
                            break
                        case "continue":
                            continue
                        case "retry":
                            raise NotImplementedError
                        case "replan":
                            raise NotImplementedError
                        case "abort":
                            state.done = True
                            break
                        case _:
                            raise NotImplementedError

            return state
