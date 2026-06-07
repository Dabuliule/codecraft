from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from codecraft.core.session_store import SessionStore
from codecraft.cli.ui.session_renderer import SessionRenderer, last_answer
from codecraft.cli.ui.status_renderer import StatusRenderer

if TYPE_CHECKING:
    from codecraft.cli.shell.context import ShellContext


@dataclass(frozen=True)
class SlashCommandResult:
    handled: bool
    should_exit: bool = False
    exit_code: int = 0


class SlashCommandHandler(Protocol):
    async def __call__(self, args: list[str], context: "ShellContext") -> SlashCommandResult:
        ...


class SlashCommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, SlashCommandHandler] = {}

    def register(self, name: str, handler: SlashCommandHandler) -> None:
        self._handlers[name] = handler

    def is_slash_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    async def handle(self, text: str, context: "ShellContext") -> SlashCommandResult:
        parts = text.strip().split()
        name = parts[0][1:]
        args = parts[1:]
        handler = self._handlers.get(name)
        if handler is None:
            context.renderer.render_unknown_slash_command(name)
            return SlashCommandResult(handled=False)
        return await handler(args, context)


def build_default_router() -> SlashCommandRouter:
    router = SlashCommandRouter()
    router.register("help", help_command)
    router.register("status", status_command)
    router.register("tools", tools_command)
    router.register("sessions", sessions_command)
    router.register("inspect", inspect_command)
    router.register("clear", clear_command)
    router.register("model", model_command)
    router.register("approval", approval_command)
    router.register("config", config_command)
    router.register("exit", exit_command)
    router.register("quit", exit_command)
    return router


async def help_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    table = Table.grid(padding=(0, 3))
    table.add_column(style="cyan")
    table.add_column()
    for name, description in [
        ("/help", "Show local commands"),
        ("/status", "Show current session status"),
        ("/tools", "Show registered tools"),
        ("/sessions", "Show recent sessions"),
        ("/inspect", "Inspect current session"),
        ("/clear", "Clear terminal output"),
        ("/exit", "Exit CodeCraft"),
    ]:
        table.add_row(name, description)
    context.console.print(Panel(table, title="CodeCraft commands", border_style="cyan"))
    return SlashCommandResult(handled=True)


async def status_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    StatusRenderer(context.console).render_status(context.config)
    return SlashCommandResult(handled=True)


async def tools_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    StatusRenderer(context.console).render_tools(context.runtime.tool_registry)
    return SlashCommandResult(handled=True)


async def sessions_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    summaries = await SessionStore(context.config.codecraft_home).list_sessions()
    if summaries:
        SessionRenderer(context.console).render_sessions(summaries)
    else:
        context.console.print("No sessions found.")
    return SlashCommandResult(handled=True)


async def inspect_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    events = (await context.thread.read_snapshot()).events
    renderer = SessionRenderer(context.console)
    renderer.render_inspect_summary(context.config.session_id, events)
    answer = last_answer(events)
    if answer:
        context.console.print(answer)
    return SlashCommandResult(handled=True)


async def clear_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    context.console.clear()
    return SlashCommandResult(handled=True)


async def model_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    StatusRenderer(context.console).render_model(context.config)
    return SlashCommandResult(handled=True)


async def approval_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    context.console.print(f"approval_policy: {context.config.approval_policy}")
    return SlashCommandResult(handled=True)


async def config_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    StatusRenderer(context.console).render_status(context.config)
    return SlashCommandResult(handled=True)


async def exit_command(args: list[str], context: "ShellContext") -> SlashCommandResult:
    return SlashCommandResult(handled=True, should_exit=True)
