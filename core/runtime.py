from __future__ import annotations

import json

from core.executor import Executor
from core.planner import Planner
from core.reflector import Reflector
from observability.context import trace_scope
from schema.result import AgentResult
from schema.state import AgentState
from tool import ToolResult


class AgentRuntime:
    """
    Planner → Executor → Reflector 驱动的 Agent Runtime。
    只负责 orchestration（编排）。
    """

    def __init__(self, planner: Planner, executor: Executor, reflector: Reflector) -> None:
        self.planner = planner
        self.executor = executor
        self.reflector = reflector

    async def arun(self, task: str) -> AgentResult:
        state = AgentState(task=task)

        with trace_scope(trace_id=state.trace_id, component="runtime"):
            while not state.done:
                plan = await self.planner.aplan(state)
                print(plan.pretty())

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

            return AgentResult(
                success=state.done,
                answer=self._extract_answer(state),
                steps=state.history,
            )

    @staticmethod
    def _extract_answer(state: AgentState) -> str | None:
        if not state.history:
            return None

        last_step = state.history[-1]
        observation = last_step.observation

        if isinstance(observation, ToolResult):
            if observation.content:
                return observation.content
            if observation.error:
                return observation.error
            return None

        if isinstance(observation, str):
            return observation

        try:
            return json.dumps(observation, ensure_ascii=False, default=str)
        except Exception:
            return str(observation)
