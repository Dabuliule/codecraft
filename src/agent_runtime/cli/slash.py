from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich import box
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from agent_runtime.tool.base import ToolResult
from agent_runtime.schema.state import AgentState


@dataclass(frozen=True)
class SlashCommandResult:
    should_exit: bool = False


class SlashCommandHandler:
    def __init__(
            self,
            *,
            console: Console,
            get_state: Callable[[], AgentState | None],
            get_verbose: Callable[[], bool],
            set_verbose: Callable[[bool], None],
            render_welcome: Callable[[], None],
            max_output_chars: int = 1200,
    ) -> None:
        self.console = console
        self.get_state = get_state
        self.get_verbose = get_verbose
        self.set_verbose = set_verbose
        self.render_welcome = render_welcome
        self.max_output_chars = max_output_chars

    async def handle(
            self,
            raw_input: str,
    ) -> SlashCommandResult:
        command = raw_input.strip().split(maxsplit=1)[0]

        match command:
            case "/help":
                self._render_help()
            case "/status":
                self._render_status()
            case "/exit":
                return SlashCommandResult(should_exit=True)
            case "/clear":
                self.console.clear()
                self.render_welcome()
            case "/history":
                self._render_history()
            case "/plan":
                self._render_plan()
            case "/diff":
                self._render_diff()
            case "/verbose":
                self._toggle_verbose()
            case _:
                self._render_unknown(command)

        return SlashCommandResult()

    def _render_help(self) -> None:
        commands = [
            ("/help", "show commands"),
            ("/status", "show current runtime status"),
            ("/exit", "quit"),
            ("/clear", "clear the screen"),
            ("/history", "show recent steps"),
            ("/verbose", "toggle detailed event rendering"),
        ]

        if self._has_plan():
            commands.append(("/plan", "show current tool plan"))

        if self._latest_diff():
            commands.append(("/diff", "show latest diff"))

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan")
        table.add_column()

        for name, description in commands:
            table.add_row(name, description)

        self.console.print(
            self._panel(
                table,
                title="Slash Commands",
                border_style="blue",
            )
        )

    def _render_status(self) -> None:
        state = self.get_state()
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()

        table.add_row("trace_id", state.trace_id if state else "-")
        table.add_row("cwd", os.getcwd())
        table.add_row("done", str(state.done) if state else "-")
        table.add_row(
            "history_steps",
            str(len(state.recent_steps)) if state else "0",
        )
        table.add_row("has_plan", str(self._has_plan()))
        table.add_row("has_diff", str(bool(self._latest_diff())))

        self.console.print(
            self._panel(
                table,
                title="Status",
                border_style="green",
            )
        )

    def _render_history(self) -> None:
        state = self.get_state()

        if not state or not state.recent_steps:
            self._render_info("No history yet.")
            return

        table = Table(
            show_header=True,
            header_style="bold",
            box=box.SIMPLE,
        )
        table.add_column("Step", no_wrap=True)
        table.add_column("OK", no_wrap=True)
        table.add_column("Tool")
        table.add_column("Summary")

        for step in state.recent_steps[-8:]:
            table.add_row(
                step.step_id,
                "yes" if step.success else "no",
                step.tool_call.tool,
                self._truncate(step.summary, limit=140),
            )

        self.console.print(
            self._panel(
                table,
                title="History",
                border_style="cyan",
            )
        )

    def _render_plan(self) -> None:
        state = self.get_state()

        if not state or not state.current_decision:
            self._render_info("No current plan available.")
            return

        plan = state.current_decision.plan.model_dump()

        self.console.print(
            self._panel(
                self._json_syntax(plan),
                title="Plan",
                border_style="yellow",
            )
        )

    def _render_diff(self) -> None:
        diff = self._latest_diff()

        if not diff:
            self._render_info("No diff available in the current session.")
            return

        self.console.print(
            self._panel(
                Syntax(
                    self._truncate(diff),
                    "diff",
                    theme="ansi_dark",
                    word_wrap=True,
                ),
                title="Diff",
                border_style="magenta",
            )
        )

    def _toggle_verbose(self) -> None:
        verbose = not self.get_verbose()
        self.set_verbose(verbose)
        mode = "verbose" if verbose else "friendly"
        self.console.print(f"[green]Mode:[/green] {mode}")

    def _render_unknown(
            self,
            command: str,
    ) -> None:
        self.console.print(
            self._panel(
                Text(
                    f"Unknown command: {command}\n"
                    "Type /help to see available commands."
                ),
                title="Command",
                border_style="yellow",
            )
        )

    def _render_info(
            self,
            message: str,
    ) -> None:
        self.console.print(
            self._panel(
                Text(message),
                title="Info",
                border_style="blue",
            )
        )

    def _has_plan(self) -> bool:
        state = self.get_state()
        return bool(state and state.current_decision)

    def _latest_diff(self) -> str | None:
        state = self.get_state()

        if not state:
            return None

        for step in reversed(state.recent_steps):
            content = self._observation_content(step.observation)

            if content and self._looks_like_diff(content):
                return content

        return None

    @staticmethod
    def _observation_content(
            observation: Any,
    ) -> str:
        if isinstance(observation, ToolResult):
            return observation.content

        if isinstance(observation, str):
            return observation

        try:
            return json.dumps(
                observation,
                ensure_ascii=False,
                default=str,
            )
        except Exception:
            return str(observation)

    @staticmethod
    def _looks_like_diff(
            content: str,
    ) -> bool:
        lines = content.splitlines()

        if not lines:
            return False

        markers = ("diff --git ", "--- ", "+++ ", "@@ ")
        return any(line.startswith(markers) for line in lines[:12])

    def _json_syntax(
            self,
            value: Any,
    ) -> Syntax:
        return Syntax(
            self._truncate(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            ),
            "json",
            theme="ansi_dark",
            word_wrap=True,
        )

    def _truncate(
            self,
            content: str,
            *,
            limit: int | None = None,
    ) -> str:
        max_chars = limit or self.max_output_chars
        text = content.strip()

        if len(text) <= max_chars:
            return text

        omitted = len(text) - max_chars
        return f"{text[:max_chars].rstrip()}\n... truncated {omitted} chars"

    @staticmethod
    def _panel(
            body: RenderableType,
            *,
            title: str,
            border_style: str,
    ) -> Panel:
        return Panel(
            body,
            title=title,
            border_style=border_style,
            box=box.ROUNDED,
        )
