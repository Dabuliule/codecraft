from llm.base import BaseLLM
from memory.base import MemoryStore
from observability.context import trace_scope
from observability.trace import TraceLogger
from schema.memory import MemoryItem
from schema.state import AgentState


class Reflector:
    """Simple reflection step to decide whether to retry."""

    def __init__(self, llm: BaseLLM, memory: MemoryStore) -> None:
        self.llm = llm
        self.memory = memory

    def reflect(self, state: AgentState, last_output: object) -> bool:
        with trace_scope(component="reflector", step=state.current_step):
            self.memory.add(
                MemoryItem(role="user", content=f"Reflect on: {last_output}")
            )
            messages = self._build_messages(max_history=10)
            TraceLogger.log("reflect.request", {"messages": len(messages)})
            feedback = self.llm.generate(messages=messages)
            decision = "retry" in str(getattr(feedback, "content", feedback)).lower()
            TraceLogger.log(
                "reflect.decision",
                {"decision": "retry" if decision else "continue"},
            )
            return decision

    def _build_messages(self, max_history: int) -> list[dict[str, str]]:
        items = list(reversed(self.memory.recent(max_history)))
        return [{"role": item.role, "content": item.content} for item in items]
