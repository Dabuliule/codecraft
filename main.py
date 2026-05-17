import asyncio

from dotenv import load_dotenv

from core import Reflector
from core.executor import Executor
from core.planner import Planner
from core.runtime import AgentRuntime
from llm.providers.qwen import QwenLLM
from tool import ToolRegistry


async def main():
    load_dotenv()
    llm = QwenLLM(model="qwen3.6-flash-2026-04-16")

    tools = ToolRegistry()

    planner = Planner(
        llm=llm,
        tool_registry=tools,
    )

    executor = Executor(
        tool_registry=tools,
    )

    reflector = Reflector(
        llm=llm,
    )

    runtime = AgentRuntime(
        planner=planner,
        executor=executor,
        reflector=reflector,
    )

    task = "这个目录的结构是什么：/Users/wpt/project/agent/agent-runtime/"

    result = await runtime.arun(
        task=task,
    )

    print(result.pretty())


if __name__ == "__main__":
    asyncio.run(main())
