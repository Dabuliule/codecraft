from llm.base import BaseLLM
from memory.base import MemoryStore
from schema.memory import MemoryItem
from schema.state import AgentState


class Reflector:
    """Simple reflection step to decide whether to retry."""

    def __init__(self, llm: BaseLLM, memory: MemoryStore) -> None:
        self.llm = llm
        self.memory = memory

    def reflect(self, state: AgentState, last_output: object) -> bool:
        self.memory.add(
            MemoryItem(role="user", content=f"Reflect on: {last_output}")
        )
        messages = self._build_messages(max_history=10)
        feedback = self.llm.generate(messages=messages)
        return "retry" in str(getattr(feedback, "content", feedback)).lower()

    def _build_messages(self, max_history: int) -> list[dict[str, str]]:
        items = list(reversed(self.memory.recent(max_history)))
        return [{"role": item.role, "content": item.content} for item in items]
