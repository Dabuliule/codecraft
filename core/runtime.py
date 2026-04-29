from typing import Optional

from core.executor import Executor
from core.reflector import Reflector
from memory.base import MemoryStore
from memory.in_memory import InMemoryStore
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

        if not self.memory.list():
            self.memory.add(MemoryItem(role="user", content=task))

        result: Optional[object] = None
        while not state.done and state.current_step < state.max_steps:
            result = self.executor.step(state)
            if state.done:
                break
            if self.reflector and self.reflector.reflect(state, result):
                continue


        return result