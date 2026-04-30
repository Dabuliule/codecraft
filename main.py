from core import Executor
from llm.providers.qwen import QwenLLM
from memory import InMemoryStore
from schema import AgentState
from schema.memory import MemoryItem
from tool import ToolRegistry


if __name__ == "__main__":
    llm = QwenLLM(model="qwen3.6-flash-2026-04-16")
    tools = ToolRegistry()
    memory = InMemoryStore()

    executor = Executor(llm=llm, tool_registry=tools, memory=memory)

    task = "Say hello"
    memory.add(MemoryItem(role="user", content=task))
    state = AgentState(task=task, history=[], current_step=0, max_steps=1, done=False)
    result = executor.step(state)
    print("Result:", result)
