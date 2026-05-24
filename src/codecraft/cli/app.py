import asyncio
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from rich.console import Console

from codecraft.cli.rich_renderer import RichRenderer
from codecraft.cli.slash import SlashCommandHandler
from codecraft.core.approval import ApprovalBroker, ApprovalHandler
from codecraft.core.approval_gate import ApprovalGate
from codecraft.core.agent import Agent
from codecraft.core.event_bus import EventBus
from codecraft.core.tool_executor import ToolExecutor
from codecraft.core.runtime import AgentRuntime
from codecraft.core.trace import JsonlTraceWriter, TraceSummary
from codecraft.llm.providers.qwen import QwenLLM
from codecraft.policy.approval import DefaultApprovalPolicy
from codecraft.schema.approval import ApprovalDecision
from codecraft.schema.event import ApprovalRequestEvent
from codecraft.tool.factory import create_tool_registry

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
)

console = Console()
session = PromptSession()


def build_runtime(
        event_bus: EventBus | None = None,
        approval_handler: ApprovalHandler | None = None,
) -> AgentRuntime:
    llm = QwenLLM()

    tools = create_tool_registry()

    agent = Agent(
        llm=llm,
        tool_registry=tools,
    )

    executor = ToolExecutor(
        tool_registry=tools,
    )

    approval_broker = ApprovalBroker(
        handler=approval_handler,
    )

    approval_gate = ApprovalGate(
        approval_policy=DefaultApprovalPolicy(),
        approval_broker=approval_broker,
        tool_executor=executor,
    )

    return AgentRuntime(
        agent=agent,
        approval_gate=approval_gate,
        event_bus=event_bus,
    )


def render_welcome(verbose: bool) -> None:
    mode = "verbose" if verbose else "friendly"
    console.print(f"CodeCraft ({mode})")
    console.print("Type /help for commands, /exit to quit.")


def render_trace_summary(
        summary: TraceSummary,
) -> None:
    console.print(f"trace_id: {summary.trace_id}")
    console.print(f"file: {summary.path}")
    console.print(f"events: {summary.event_count}")
    console.print(f"last_event: {summary.last_event_type or '-'}")

    if summary.event_counts:
        counts = ", ".join(
            f"{name}={count}"
            for name, count in summary.event_counts.items()
        )
        console.print(f"event_counts: {counts}")

    if summary.final_answer:
        console.print(f"final_answer: {summary.final_answer}")


async def run_chat(verbose: bool = False):
    load_dotenv()

    event_bus = EventBus()
    renderer = RichRenderer(console=console, verbose=verbose)
    trace_writer = JsonlTraceWriter()
    event_bus.subscribe(renderer.handle)
    event_bus.subscribe(trace_writer.handle)

    async def request_approval(event: ApprovalRequestEvent) -> ApprovalDecision:
        answer = await session.prompt_async(
            f"approve {event.tool}? [y/N] "
        )
        approved = answer.strip().lower() in {
            "y",
            "yes",
            "approve",
            "approved",
        }
        if approved:
            return ApprovalDecision.approve("approved by user")

        return ApprovalDecision.reject("rejected by user")

    runtime = build_runtime(
        event_bus=event_bus,
        approval_handler=request_approval,
    )

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
            user_input = await session.prompt_async("codecraft > ")
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


@app.callback()
def main(
        ctx: typer.Context,
) -> None:
    if ctx.invoked_subcommand is None:
        asyncio.run(run_chat())


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


@app.command("trace-summary")
def trace_summary(
        trace: Annotated[
            str,
            typer.Argument(
                help="Trace id or path to a JSONL trace file.",
            ),
        ],
        trace_dir: Annotated[
            Path,
            typer.Option(
                "--trace-dir",
                help="Directory containing trace JSONL files.",
            ),
        ] = Path(".codecraft/traces"),
) -> None:
    writer = JsonlTraceWriter(trace_dir=trace_dir)
    summary = writer.summarize_ref(trace)

    if not summary:
        console.print(f"No trace found for {trace}")
        raise typer.Exit(code=1)

    render_trace_summary(summary)


if __name__ == "__main__":
    app()
