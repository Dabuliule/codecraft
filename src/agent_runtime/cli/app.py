import asyncio

import typer
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from rich.console import Console
from rich.panel import Panel

from agent_runtime.core.agent import Agent
from agent_runtime.core.executor import Executor
from agent_runtime.core.runtime import AgentRuntime
from agent_runtime.llm.providers.qwen import QwenLLM
from agent_runtime.schema.event import (
    ActionEvent,
    FinalResultEvent,
    ObservationEvent,
    ThoughtEvent,
    WarningEvent,
)
from agent_runtime.tool.registry import ToolRegistry

app = typer.Typer()

console = Console()
session = PromptSession()


def build_runtime() -> AgentRuntime:
    llm = QwenLLM()

    tools = ToolRegistry()

    agent = Agent(
        llm=llm,
        tool_registry=tools,
    )

    executor = Executor(
        tool_registry=tools,
    )

    return AgentRuntime(
        agent=agent,
        executor=executor,
    )


async def run_chat():
    load_dotenv()

    runtime = build_runtime()

    console.print(
        Panel.fit(
            "Agent Runtime Started",
            border_style="green",
        )
    )

    while True:
        try:
            user_input = await session.prompt_async("> ")

            if user_input.strip() in {"exit", "quit"}:
                break

            console.print()

            async for event in runtime.astream(task=user_input):
                match event:
                    case ThoughtEvent():
                        console.print(
                            Panel(
                                event.thought,
                                title="🧠 Thought",
                                border_style="cyan",
                            )
                        )

                    case ActionEvent():
                        console.print(
                            Panel(
                                f"{event.tool}\n\n"
                                f"{event.tool_input}",
                                title="🎯 Action",
                                border_style="yellow",
                            )
                        )

                    case ObservationEvent():
                        style = (
                            "green"
                            if event.success
                            else "red"
                        )

                        console.print(
                            Panel(
                                event.content[:3000],
                                title="📤 Observation",
                                border_style=style,
                            )
                        )

                    case WarningEvent():
                        console.print(
                            Panel(
                                event.message,
                                title="⚠️ Warning",
                                border_style="red",
                            )
                        )

                    case FinalResultEvent():
                        console.print()
                        console.print(event.result.pretty())
                        console.print()

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")

        except Exception as e:
            console.print(f"[red]{e}[/red]")


@app.command()
def chat():
    asyncio.run(run_chat())


if __name__ == "__main__":
    app()
