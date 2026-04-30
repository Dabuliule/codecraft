from core import Executor
from core.runtime import AgentRuntime
from llm.providers.qwen import QwenLLM
from memory import InMemoryStore
from tool import ToolRegistry

if __name__ == "__main__":
    llm = QwenLLM(model="qwen3.6-flash-2026-04-16")
    tools = ToolRegistry()
    memory = InMemoryStore()

    executor = Executor(llm=llm, tool_registry=tools, memory=memory)
    runtime = AgentRuntime(executor=executor, memory=memory)

    task = "这个文件的内容是什么：/Users/wpt/project/agent/agent-runtime/main.py"
    result = runtime.run(task, max_steps=1)
    print("Result:", result)
