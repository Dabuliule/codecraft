from __future__ import annotations

import json
from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from agent_runtime.schema.event import (
    FinalResultEvent,
    IntentRequestEvent,
    ObservationEvent,
    OperationEvent,
    RuntimeEvent,
    ThoughtEvent,
    WarningEvent,
)


class RichRenderer:
    """
    Rich renderer for runtime events.

    This class only maps RuntimeEvent instances to terminal output. It does not
    make orchestration decisions or execute operations.
    """

    def __init__(
            self,
            console: Console | None = None,
            *,
            verbose: bool = False,
            max_output_chars: int = 1200,
            max_verbose_output_chars: int = 3000,
    ) -> None:
        self.console = console or Console()
        self.verbose = verbose
        self.max_output_chars = max_output_chars
        self.max_verbose_output_chars = max_verbose_output_chars

    async def handle(
            self,
            event: RuntimeEvent,
    ) -> None:
        if isinstance(event, ThoughtEvent):
            self._render_thought(event)
            return

        if isinstance(event, IntentRequestEvent):
            self._render_intent(event)
            return

        if isinstance(event, OperationEvent):
            self._render_operation(event)
            return

        if isinstance(event, ObservationEvent):
            self._render_observation(event)
            return

        if isinstance(event, WarningEvent):
            self._render_warning(event)
            return

        if isinstance(event, FinalResultEvent):
            self._render_final(event)

    def _render_thought(
            self,
            event: ThoughtEvent,
    ) -> None:
        if self.verbose:
            body: RenderableType = self._truncate(event.thought)
        else:
            body = Text("Thinking", style="cyan")

        self.console.print(
            self._panel(
                body,
                title="Thought",
                border_style="cyan",
            )
        )

    def _render_intent(
            self,
            event: IntentRequestEvent,
    ) -> None:
        tool_input = {
            "target": event.target,
            "params": event.params,
        }

        title = f"Intent: {event.intent}"

        if self.verbose:
            body: RenderableType = self._json_syntax(tool_input)
        else:
            target = event.target.get("path") or event.target.get("command")
            summary = f"{event.intent}"
            if target:
                summary = f"{summary}\n{target}"
            body = Text(summary)

        self.console.print(
            self._panel(
                body,
                title=title,
                border_style="yellow",
            )
        )

    def _render_operation(
            self,
            event: OperationEvent,
    ) -> None:
        body: RenderableType

        if event.tool_input:
            body = Group(
                Text(f"{event.intent} -> {event.operation}"),
                self._json_syntax(event.tool_input),
            )
        else:
            body = Text(f"{event.intent} -> {event.operation}")

        self.console.print(
            self._panel(
                body,
                title="Operation",
                border_style="magenta",
            )
        )

    def _render_observation(
            self,
            event: ObservationEvent,
    ) -> None:
        border_style = "green" if event.success else "red"
        title = "Observation" if event.success else "Observation Failed"

        parts: list[RenderableType] = []

        if event.content:
            parts.append(self._render_output(event.content))

        if event.error:
            parts.append(Text(f"error: {event.error}", style="red"))

        if event.suggestion:
            parts.append(Text(f"suggestion: {event.suggestion}", style="yellow"))

        body: RenderableType
        if parts:
            body = Group(*parts)
        else:
            body = Text("Done" if event.success else "Failed")

        self.console.print(
            self._panel(
                body,
                title=title,
                border_style=border_style,
            )
        )

    def _render_warning(
            self,
            event: WarningEvent,
    ) -> None:
        self.console.print(
            self._panel(
                Text(event.message),
                title="Warning",
                border_style="red",
            )
        )

    def _render_final(
            self,
            event: FinalResultEvent,
    ) -> None:
        result = event.result
        answer = result.answer or ""

        body: RenderableType = Markdown(answer) if answer else Text("No answer")

        self.console.print(
            self._panel(
                body,
                title="Final",
                border_style="green" if result.success else "red",
            )
        )

        footer = f"Completed in {result.total_steps} step"
        if result.total_steps != 1:
            footer = f"{footer}s"

        if result.warnings:
            footer = f"{footer}; warnings: {len(result.warnings)}"

        self.console.print(Text(footer, style="dim"))
        self.console.print()

    def _render_output(
            self,
            content: str,
    ) -> RenderableType:
        text = self._truncate(content)

        if self._looks_like_diff(text):
            return Syntax(
                text,
                "diff",
                theme="ansi_dark",
                word_wrap=True,
            )

        return Text(text)

    def _truncate(
            self,
            content: str,
    ) -> str:
        limit = (
            self.max_verbose_output_chars
            if self.verbose
            else self.max_output_chars
        )

        text = content.strip()

        if len(text) <= limit:
            return text

        omitted = len(text) - limit
        return f"{text[:limit].rstrip()}\n... truncated {omitted} chars"

    @staticmethod
    def _looks_like_diff(
            content: str,
    ) -> bool:
        lines = content.splitlines()

        if not lines:
            return False

        markers = ("diff --git ", "--- ", "+++ ", "@@ ")
        return any(line.startswith(markers) for line in lines[:12])

    @staticmethod
    def _json(
            value: Any,
    ) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    def _json_syntax(
            self,
            value: Any,
    ) -> Syntax:
        return Syntax(
            self._truncate(self._json(value)),
            "json",
            theme="ansi_dark",
            word_wrap=True,
        )

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
