from typing import Optional

from core.executor import Executor
from core.reflector import Reflector
from memory.base import MemoryStore
from memory.in_memory import InMemoryStore
from observability.context import trace_scope
from observability.trace import TraceLogger
from schema.memory import MemoryItem
from schema.state import AgentState


class AgentRuntime:
    """Run an agent loop with optional reflection."""

    def __init__(
        self,
        executor: Executor,
        reflector: Optional[Reflector] = None,
        memory: Optional[MemoryStore] = None,
    ) -> None:
        self.executor = executor
        self.reflector = reflector
        self.memory = memory or InMemoryStore()

    def run(self, task: str, *, max_steps: Optional[int] = None) -> Optional[object]:
        state = AgentState(task=task)
        if max_steps is not None:
            state.max_steps = max_steps

        with trace_scope(trace_id=state.trace_id, component="runtime"):
            TraceLogger.log(
                "runtime.start",
                {"task": task, "max_steps": state.max_steps},
            )

            if not self.memory.list():
                self.memory.add(MemoryItem(role="user", content=task))
                TraceLogger.log("runtime.memory.seed", {"role": "user"})

            result: Optional[object] = None
            while not state.done and state.current_step < state.max_steps:
                with trace_scope(step=state.current_step, component="runtime"):
                    TraceLogger.log(
                        "runtime.step.start",
                        {"current_step": state.current_step},
                    )
                    result = self.executor.step(state)
                    TraceLogger.log(
                        "runtime.step.end",
                        {"done": state.done, "result_type": type(result).__name__},
                    )
                if state.done:
                    break
                if self.reflector:
                    with trace_scope(step=state.current_step, component="runtime"):
                        TraceLogger.log(
                            "runtime.reflect.start",
                            {"last_output_type": type(result).__name__},
                        )
                    if self.reflector.reflect(state, result):
                        with trace_scope(step=state.current_step, component="runtime"):
                            TraceLogger.log("runtime.reflect.retry", {"decision": "retry"})
                        continue

            TraceLogger.log(
                "runtime.done",
                {"done": state.done, "steps": state.current_step},
            )
            return result

