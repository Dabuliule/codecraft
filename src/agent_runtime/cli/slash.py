from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.console import Console

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

        self.console.print("commands:")
        for name, description in commands:
            self.console.print(f"  {name:<10} {description}")

    def _render_status(self) -> None:
        state = self.get_state()
        self.console.print(f"trace_id: {state.trace_id if state else '-'}")
        self.console.print(f"cwd: {os.getcwd()}")
        self.console.print(f"done: {state.done if state else '-'}")
        self.console.print(f"history_steps: {len(state.recent_steps) if state else 0}")
        self.console.print(f"has_plan: {self._has_plan()}")
        self.console.print(f"has_diff: {bool(self._latest_diff())}")

    def _render_history(self) -> None:
        state = self.get_state()

        if not state or not state.recent_steps:
            self._render_info("No history yet.")
            return

        for step in state.recent_steps[-8:]:
            ok = "ok" if step.success else "failed"
            summary = self._truncate(step.summary, limit=140)
            self.console.print(f"{step.step_id} {ok} {step.tool_call.tool}: {summary}")

    def _render_plan(self) -> None:
        state = self.get_state()

        if not state or not state.current_decision:
            self._render_info("No current plan available.")
            return

        plan = state.current_decision.plan.model_dump()

        self.console.print(self._json(plan))

    def _render_diff(self) -> None:
        diff = self._latest_diff()

        if not diff:
            self._render_info("No diff available in the current session.")
            return

        self.console.print(self._truncate(diff))

    def _toggle_verbose(self) -> None:
        verbose = not self.get_verbose()
        self.set_verbose(verbose)
        mode = "verbose" if verbose else "friendly"
        self.console.print(f"mode: {mode}")

    def _render_unknown(
            self,
            command: str,
    ) -> None:
        self.console.print(f"Unknown command: {command}")
        self.console.print("Type /help to see available commands.")

    def _render_info(
            self,
            message: str,
    ) -> None:
        self.console.print(message)

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

    def _json(
            self,
            value: Any,
    ) -> str:
        return self._truncate(
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
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
