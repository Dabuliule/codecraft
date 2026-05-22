from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.text import Text

from agent_runtime.schema.event import (
    FinalResultEvent,
    ObservationEvent,
    RuntimeEvent,
    ThoughtEvent,
    ToolCallEvent,
    ToolExecutionEvent,
    WarningEvent,
)


class RichRenderer:
    """
    Rich renderer for runtime events.

    This class only maps RuntimeEvent instances to terminal output. It does not
    make orchestration decisions or execute tools.
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

        if isinstance(event, ToolCallEvent):
            self._render_tool_call(event)
            return

        if isinstance(event, ToolExecutionEvent):
            self._render_tool_execution(event)
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
            self.console.print(f"thought: {self._truncate(event.thought)}")

    def _render_tool_call(
            self,
            event: ToolCallEvent,
    ) -> None:
        if self.verbose:
            self.console.print(f"tool: {event.tool}")
            if event.args:
                self.console.print(self._json(event.args))
        else:
            target = event.args.get("path") or event.args.get("command")
            summary = f"{event.tool}"
            if target:
                summary = f"{summary} {target}"
            self.console.print(f"tool: {summary}")

    def _render_tool_execution(
            self,
            event: ToolExecutionEvent,
    ) -> None:
        if self.verbose and event.tool_input:
            self.console.print(f"run: {event.tool}")
            self.console.print(self._json(event.tool_input))

    def _render_observation(
            self,
            event: ObservationEvent,
    ) -> None:
        policy_action = self._policy_action(event)

        if policy_action == "require_approval":
            self.console.print(Text("approval required", style="yellow bold"))

        if event.content and (self.verbose or not event.success):
            self.console.print(self._render_output(event.content))

        if event.error:
            style = "yellow" if policy_action == "require_approval" else "red"
            self.console.print(Text(f"error: {event.error}", style=style))

        if event.suggestion:
            self.console.print(Text(f"suggestion: {event.suggestion}", style="yellow"))

    def _render_warning(
            self,
            event: WarningEvent,
    ) -> None:
        self.console.print(Text(f"warning: {event.message}", style="yellow"))

    def _render_final(
            self,
            event: FinalResultEvent,
    ) -> None:
        result = event.result
        answer = result.answer or ""

        if answer:
            self.console.print(answer)
        else:
            self.console.print("No answer")

        footer = f"Completed in {result.total_steps} step"
        if result.total_steps != 1:
            footer = f"{footer}s"

        if result.warnings:
            footer = f"{footer}; warnings: {len(result.warnings)}"

        if self.verbose:
            self.console.print(Text(footer, style="dim"))
            self.console.print()

    def _render_output(
            self,
            content: str,
    ) -> str:
        text = self._truncate(content)
        return text

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
    def _json(
            value: Any,
    ) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    @staticmethod
    def _policy_action(
            event: ObservationEvent,
    ) -> str | None:
        if not isinstance(event.data, dict):
            return None

        policy = event.data.get("policy")
        if not isinstance(policy, dict):
            return None

        action = policy.get("action")
        if not isinstance(action, str):
            return None

        return action
