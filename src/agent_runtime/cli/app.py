import asyncio
from typing import Annotated

import typer
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent_runtime.core.agent import Agent
from agent_runtime.core.event_bus import EventBus
from agent_runtime.core.executor import Executor
from agent_runtime.core.runtime import AgentRuntime
from agent_runtime.cli.rich_renderer import RichRenderer
from agent_runtime.llm.providers.qwen import QwenLLM
from agent_runtime.operation.registry import OperationRegistry

app = typer.Typer()

console = Console()
session = PromptSession()


HELP_TEXT = """\
Commands:
  /help      show commands
  /verbose   toggle detailed event panels
  /clear     clear the screen
  exit       quit
"""


def build_runtime(
        event_bus: EventBus | None = None,
) -> AgentRuntime:
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
        event_bus=event_bus,
    )


def render_welcome(verbose: bool) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold green")
    table.add_column()
    table.add_row("Agent Runtime", "interactive session")
    table.add_row("Mode", "verbose" if verbose else "friendly")
    table.add_row("Commands", "/help, /verbose, /clear, exit")

    console.print(
        Panel(
            table,
            border_style="green",
            box=box.ROUNDED,
        )
    )


def render_help() -> None:
    console.print(
        Panel(
            HELP_TEXT,
            title="Help",
            border_style="blue",
            box=box.ROUNDED,
        )
    )


async def run_chat(verbose: bool = False):
    load_dotenv()

    event_bus = EventBus()
    renderer = RichRenderer(console=console, verbose=verbose)
    event_bus.subscribe(renderer.handle)
    runtime = build_runtime(event_bus=event_bus)

    render_welcome(verbose=verbose)

    while True:
        try:
            user_input = await session.prompt_async("agent > ")
            command = user_input.strip()

            if command in {"exit", "quit"}:
                break

            if command == "/help":
                render_help()
                continue

            if command == "/clear":
                console.clear()
                render_welcome(verbose=verbose)
                continue

            if command == "/verbose":
                verbose = not verbose
                renderer.verbose = verbose
                mode = "verbose" if verbose else "friendly"
                console.print(f"[green]Mode:[/green] {mode}")
                continue

            if not command:
                continue

            console.print()

            async for _ in runtime.astream(task=user_input):
                pass

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")

        except Exception as e:
            console.print(f"[red]{e}[/red]")


@app.command()
def chat(
        verbose: Annotated[
            bool,
            typer.Option(
                "--verbose",
                "-v",
                help="Show full thought, intent, operation, and observation panels.",
            ),
        ] = False,
):
    asyncio.run(run_chat(verbose=verbose))


if __name__ == "__main__":
    app()
