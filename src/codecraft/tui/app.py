from __future__ import annotations

import json
from typing import Any

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Header, Input, Label, RichLog, Static

from codecraft.cli.shell.runner import shutdown_thread
from codecraft.core.errors import CodecraftError
from codecraft.core.ids import new_id
from codecraft.core.runtime import AgentRuntime
from codecraft.core.thread import AgentThread
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.session import SessionConfig


class MessageBlock(Static):
    def __init__(self, role: str, text: str = "") -> None:
        super().__init__(classes=role.casefold())
        self.role = role
        self.text = text

    def set_text(self, text: str) -> None:
        self.text = text
        self.refresh(layout=True)

    def render(self) -> RenderableType:
        role_style = {
            "User": "bold #7bdff2",
            "Assistant": "bold #72d6a0",
            "Error": "bold #ef6b73",
        }.get(self.role, "bold #d7a95b")
        body: RenderableType = (
            Markdown(self.text) if self.role == "Assistant" else Text(self.text)
        )
        return Group(Text(self.role, style=role_style), body)


class ApprovalScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "reject", show=False)]

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self.payload = payload

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-dialog"):
            yield Label("Approval required", id="approval-title")
            yield Static(_approval_details(self.payload), id="approval-details")
            with Horizontal(id="approval-actions"):
                yield Button("Reject", variant="error", id="reject")
                yield Button("Approve", variant="success", id="approve")

    def on_mount(self) -> None:
        self.query_one("#reject", Button).focus()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")

    def action_reject(self) -> None:
        self.dismiss(False)


class CodeCraftTUI(App[None]):
    TITLE = "CodeCraft"
    BINDINGS = [
        Binding("ctrl+q", "quit", show=False, priority=True),
        Binding("ctrl+c", "quit", show=False, priority=True),
    ]

    CSS = """
    Screen {
        background: #111315;
        color: #d9dde3;
    }

    Header {
        background: #181b1f;
        color: #f4f6f8;
    }

    #main {
        height: 1fr;
    }

    #conversation-pane {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        scrollbar-color: #4ec9b0;
        scrollbar-background: #181b1f;
    }

    MessageBlock {
        width: 1fr;
        height: auto;
        min-height: 3;
        padding: 1 2;
        margin-bottom: 1;
        background: #181b1f;
        border-left: thick #d7a95b;
    }

    MessageBlock.user {
        background: #171d21;
        border-left: thick #4eb6c2;
    }

    MessageBlock.assistant {
        background: #171c19;
        border-left: thick #4eaf78;
    }

    MessageBlock.error {
        background: #211719;
        border-left: thick #ef6b73;
    }

    #side-panel {
        width: 38;
        min-width: 30;
        height: 1fr;
        background: #16191c;
        border-left: solid #3a4148;
    }

    .panel-title {
        height: 2;
        padding: 0 1;
        color: #d7a95b;
        text-style: bold;
        content-align-vertical: middle;
    }

    #runtime-status {
        height: auto;
        min-height: 9;
        padding: 0 1 1 1;
        border-bottom: solid #3a4148;
    }

    #tool-log {
        height: 1fr;
        min-width: 1;
        padding: 0 1;
        scrollbar-color: #d7a95b;
        scrollbar-background: #181b1f;
    }

    #prompt {
        dock: bottom;
        height: 3;
        padding: 0 1;
        border: tall #4eaf78;
        background: #181b1f;
        color: #f4f6f8;
    }

    #prompt:focus {
        border: tall #7bdff2;
    }

    ApprovalScreen {
        align: center middle;
        background: #000000 55%;
    }

    #approval-dialog {
        width: 72;
        max-width: 92%;
        height: auto;
        max-height: 82%;
        padding: 1 2;
        background: #1c1b18;
        border: solid #d7a95b;
    }

    #approval-title {
        height: 2;
        color: #f0c674;
        text-style: bold;
    }

    #approval-details {
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }

    #approval-actions {
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }

    #approval-actions Button {
        width: 14;
        margin-left: 1;
    }
    """

    def __init__(self, config: SessionConfig, runtime: AgentRuntime) -> None:
        super().__init__()
        self.config = config
        self.runtime = runtime
        self.thread: AgentThread | None = None
        self.turn_status = "starting"
        self.token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        self._assistant_block: MessageBlock | None = None
        self._assistant_buffer = ""
        self._closed = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            yield VerticalScroll(id="conversation-pane")
            with Vertical(id="side-panel"):
                yield Label("Runtime", classes="panel-title")
                yield Static(id="runtime-status")
                yield Label("Tool activity", classes="panel-title")
                yield RichLog(
                    id="tool-log",
                    min_width=1,
                    wrap=True,
                    markup=True,
                    auto_scroll=True,
                )
        yield Input(placeholder="Message CodeCraft", id="prompt", disabled=True)

    async def on_mount(self) -> None:
        self.sub_title = f"{self.config.model_provider}/{self.config.model}"
        self._refresh_status()
        try:
            self.thread = await self.runtime.create_thread(self.config)
        except CodecraftError as exc:
            await self._show_startup_error(exc.message, exc.suggestion)
            return
        except Exception as exc:
            await self._show_startup_error(
                "Runtime could not start.", f"{type(exc).__name__}: {exc}"
            )
            return

        self.turn_status = "idle"
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()
        self._refresh_status()
        self.run_worker(
            self._consume_events(),
            group="runtime-events",
            exclusive=True,
            name="runtime-events",
        )

    @on(Input.Submitted, "#prompt")
    async def on_prompt_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or self.thread is None or self.turn_status != "idle":
            return
        event.input.value = ""
        event.input.disabled = True
        self.turn_status = "running"
        self._refresh_status()
        try:
            await self.thread.submit(SessionInput.user_message(new_id("inp_"), text))
        except Exception as exc:
            await self._append_message("Error", f"Could not submit message: {exc}")
            self._finish_turn("failed")

    async def action_quit(self) -> None:
        await self._shutdown_runtime()
        self.exit()

    async def on_unmount(self) -> None:
        await self._shutdown_runtime()

    async def _consume_events(self) -> None:
        if self.thread is None:
            return
        while True:
            event = await self.thread.next_event()
            await self._handle_event(event)
            if event.type == RuntimeEventType.SESSION_CLOSED:
                return

    async def _handle_event(self, event: RuntimeEvent) -> None:
        payload = event.payload
        if event.type == RuntimeEventType.USER_MESSAGE:
            text = payload.get("text")
            if isinstance(text, str):
                await self._append_message("User", text)
        elif event.type == RuntimeEventType.ASSISTANT_MESSAGE_DELTA:
            delta = payload.get("text")
            if isinstance(delta, str):
                self._assistant_buffer += delta
                if self._assistant_block is None:
                    self._assistant_block = await self._append_message("Assistant", "")
                self._assistant_block.set_text(self._assistant_buffer)
                self._scroll_conversation()
        elif event.type == RuntimeEventType.ASSISTANT_MESSAGE:
            text = payload.get("text")
            if isinstance(text, str):
                if self._assistant_block is None:
                    self._assistant_block = await self._append_message(
                        "Assistant", text
                    )
                else:
                    self._assistant_block.set_text(text)
                self._assistant_block = None
                self._assistant_buffer = ""
                self._scroll_conversation()
        elif event.type == RuntimeEventType.TOOL_CALL_STARTED:
            self._render_tool_started(payload)
        elif event.type == RuntimeEventType.TOOL_CALL_FINISHED:
            self._render_tool_finished(payload)
        elif event.type == RuntimeEventType.APPROVAL_REQUESTED:
            await self._request_approval(payload)
        elif event.type == RuntimeEventType.TOKEN_COUNT:
            self._add_token_usage(payload)
        elif event.type == RuntimeEventType.CONTEXT_COMPACTED:
            self._tool_log().write("[yellow]context compacted[/yellow]")
        elif event.type == RuntimeEventType.ERROR:
            message = str(payload.get("message") or payload.get("code") or "Error")
            await self._append_message("Error", message)
        elif event.type == RuntimeEventType.TURN_ABORTED:
            message = str(payload.get("message") or payload.get("reason") or "Aborted")
            await self._append_message("Error", message)
            self._finish_turn("aborted")
        elif event.type == RuntimeEventType.TURN_FINISHED:
            self._finish_turn("idle")
        elif event.type == RuntimeEventType.SESSION_CLOSED:
            self.turn_status = "closed"
            self._refresh_status()

    async def _request_approval(self, payload: dict[str, Any]) -> None:
        if self.thread is None:
            return
        self.turn_status = "approval"
        self._refresh_status()
        approved = await self.push_screen_wait(ApprovalScreen(payload))
        decision = SessionInput.approval_decision(
            new_id("inp_"),
            approval_id=str(payload["approval_id"]),
            approved=approved,
            reason="approved by TUI" if approved else "rejected by TUI",
        )
        await self.thread.submit(decision)
        label = "approved" if approved else "rejected"
        style = "green" if approved else "red"
        self._tool_log().write(f"[{style}]approval {label}[/{style}]")
        self.turn_status = "running"
        self._refresh_status()

    async def _append_message(self, role: str, text: str) -> MessageBlock:
        block = MessageBlock(role, text)
        await self.query_one("#conversation-pane", VerticalScroll).mount(block)
        self._scroll_conversation()
        return block

    def _scroll_conversation(self) -> None:
        self.query_one("#conversation-pane", VerticalScroll).scroll_end(animate=False)

    def _render_tool_started(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "tool")
        arguments = payload.get("arguments")
        suffix = ""
        if isinstance(arguments, dict) and arguments:
            compact = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
            suffix = f" {compact[:180]}"
        self._tool_log().write(f"[yellow][running][/yellow] {name}{suffix}")

    def _render_tool_finished(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "tool")
        duration = payload.get("duration_ms")
        result = payload.get("result")
        success = isinstance(result, dict) and result.get("success") is True
        status = "ok" if success else "failed"
        style = "green" if success else "red"
        elapsed = f" {duration}ms" if isinstance(duration, int) else ""
        self._tool_log().write(f"[{style}][{status}][/{style}] {name}{elapsed}")
        if not success and isinstance(result, dict):
            content = str(result.get("content") or result.get("error") or "")
            if content:
                self._tool_log().write(Text(content[:500], style="#ef9a9a"))

    def _add_token_usage(self, payload: dict[str, Any]) -> None:
        for name in self.token_usage:
            value = payload.get(name)
            if isinstance(value, int):
                self.token_usage[name] += value
        self._refresh_status()

    def _finish_turn(self, status: str) -> None:
        self.turn_status = status
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = status != "idle"
        if status == "idle":
            prompt.focus()
        self._refresh_status()

    def _refresh_status(self) -> None:
        status = self.query_one("#runtime-status", Static)
        status.update(_runtime_status(self.config, self.turn_status, self.token_usage))

    def _tool_log(self) -> RichLog:
        return self.query_one("#tool-log", RichLog)

    async def _show_startup_error(self, message: str, suggestion: str | None) -> None:
        self.turn_status = "failed"
        self._refresh_status()
        await self._append_message(
            "Error", message if not suggestion else f"{message}\n{suggestion}"
        )

    async def _shutdown_runtime(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.thread is not None:
            try:
                await shutdown_thread(self.thread)
            except Exception:
                pass
        try:
            await self.runtime.close()
        except Exception:
            pass


def _runtime_status(
    config: SessionConfig,
    status: str,
    token_usage: dict[str, int],
) -> Table:
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(style="#8f98a3", width=9)
    table.add_column(ratio=1)
    table.add_row("status", _ellipsized(status, style="bold #d7a95b"))
    table.add_row("model", _ellipsized(config.model))
    table.add_row("provider", _ellipsized(config.model_provider))
    table.add_row("sandbox", _ellipsized(str(config.sandbox_mode)))
    table.add_row("backend", _ellipsized(str(config.sandbox_backend)))
    table.add_row("MCP", str(len(config.mcp_servers)))
    table.add_row("tokens", f"{token_usage['total_tokens']:,}")
    table.add_row("session", _ellipsized(config.session_id))
    return table


def _ellipsized(value: str, *, style: str | None = None) -> Text:
    return Text(value, style=style, no_wrap=True, overflow="ellipsis")


def _approval_details(payload: dict[str, Any]) -> Group:
    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column(style="#9ca3ad", width=10)
    table.add_column(ratio=1)
    table.add_row("tool", str(payload.get("tool_name") or "-"))
    table.add_row("risk", str(payload.get("risk") or "-"))
    table.add_row("reason", str(payload.get("reason") or "-"))
    arguments = payload.get("arguments")
    details = ""
    if isinstance(arguments, dict) and arguments:
        details = json.dumps(arguments, ensure_ascii=False, indent=2, sort_keys=True)
        if len(details) > 2_000:
            details = details[:2_000] + "\n[truncated]"
    return Group(table, Text(details, style="#d9dde3"))
