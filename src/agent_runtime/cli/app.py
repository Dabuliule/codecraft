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
from agent_runtime.operation.registry import OperationRegistry
from agent_runtime.schema.event import (
    FinalResultEvent,
    IntentRequestEvent,
    ObservationEvent,
    OperationEvent,
    ThoughtEvent,
    WarningEvent,
)

app = typer.Typer()

console = Console()
session = PromptSession()


def build_runtime() -> AgentRuntime:
    llm = QwenLLM()

    operations = OperationRegistry()

    agent = Agent(
        llm=llm,
        operation_registry=operations,
    )

    executor = Executor(
        operation_registry=operations,
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

                    case IntentRequestEvent():
                        console.print(
                            Panel(
                                f"{event.intent}\n\n"
                                f"target={event.target}\n"
                                f"params={event.params}",
                                title="🎯 Intent",
                                border_style="yellow",
                            )
                        )

                    case OperationEvent():
                        console.print(
                            Panel(
                                f"{event.intent} -> {event.operation}",
                                title="⚙️ Operation",
                                border_style="magenta",
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
