import asyncio

import typer
from dotenv import load_dotenv
from prompt_toolkit import prompt
from rich.console import Console

from core import Reflector
from core.executor import Executor
from core.planner import Planner
from core.runtime import AgentRuntime
from llm.providers.qwen import QwenLLM
from tool import ToolRegistry

app = typer.Typer()

console = Console()


def build_runtime() -> AgentRuntime:
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

    return AgentRuntime(
        planner=planner,
        executor=executor,
        reflector=reflector,
    )


@app.command()
def chat():
    load_dotenv()

    runtime = build_runtime()

    console.print("[bold green]Agent Runtime Started[/bold green]")

    while True:
        try:
            user_input = prompt("> ")

            if user_input.strip() in {"exit", "quit"}:
                break

            result = asyncio.run(
                runtime.arun(task=user_input)
            )

            console.print(result.pretty())

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")

        except Exception as e:
            console.print(f"[red]{e}[/red]")


if __name__ == "__main__":
    app()
