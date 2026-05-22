import asyncio
from typing import Annotated

import typer
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from rich.console import Console

from agent_runtime.core.agent import Agent
from agent_runtime.core.event_bus import EventBus
from agent_runtime.core.executor import Executor
from agent_runtime.core.runtime import AgentRuntime
from agent_runtime.core.trace import JsonlTraceWriter
from agent_runtime.cli.rich_renderer import RichRenderer
from agent_runtime.cli.slash import SlashCommandHandler
from agent_runtime.llm.providers.qwen import QwenLLM
from agent_runtime.tool.factory import create_tool_registry

app = typer.Typer()

console = Console()
session = PromptSession()


def build_runtime(
        event_bus: EventBus | None = None,
) -> AgentRuntime:
    llm = QwenLLM()

    tools = create_tool_registry()

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
        event_bus=event_bus,
    )


def render_welcome(verbose: bool) -> None:
    mode = "verbose" if verbose else "friendly"
    console.print(f"Agent Runtime ({mode})")
    console.print("Type /help for commands, /exit to quit.")

async def run_chat(verbose: bool = False):
    load_dotenv()

    event_bus = EventBus()
    renderer = RichRenderer(console=console, verbose=verbose)
    trace_writer = JsonlTraceWriter()
    event_bus.subscribe(renderer.handle)
    event_bus.subscribe(trace_writer.handle)
    runtime = build_runtime(event_bus=event_bus)

    def set_verbose(value: bool) -> None:
        nonlocal verbose
        verbose = value
        renderer.verbose = value

    slash_handler = SlashCommandHandler(
        console=console,
        get_state=lambda: runtime.current_state,
        get_verbose=lambda: verbose,
        set_verbose=set_verbose,
        render_welcome=lambda: render_welcome(verbose=verbose),
        trace_writer=trace_writer,
    )

    render_welcome(verbose=verbose)

    while True:
        try:
            user_input = await session.prompt_async("agent > ")
            command = user_input.strip()

            if command in {"exit", "quit"}:
                break

            if not command:
                continue

            if command.startswith("/"):
                result = await slash_handler.handle(command)
                if result.should_exit:
                    break
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
                help="Show full thought, tool, and observation panels.",
            ),
        ] = False,
):
    asyncio.run(run_chat(verbose=verbose))


if __name__ == "__main__":
    app()
