from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Header, Input, Label, RichLog, Static

from codecraft.cli.shell.runner import shutdown_thread
from codecraft.core.errors import CodecraftError
from codecraft.core.ids import new_id
from codecraft.core.runtime import AgentRuntime
from codecraft.core.thread import AgentThread
from codecraft.core.trace_report import build_trace_report
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.session import SessionConfig, SessionSummary


MAX_RESTORED_MESSAGES = 100
MAX_RESTORED_TOOL_EVENTS = 200


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


class SessionBrowserScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "new_session", show=False)]

    def __init__(self, summaries: list[SessionSummary]) -> None:
        super().__init__()
        self.summaries = summaries

    def compose(self) -> ComposeResult:
        with Vertical(id="session-dialog"):
            yield Label("Sessions", id="session-title")
            yield DataTable(
                id="session-table",
                cursor_type="row",
                zebra_stripes=True,
            )
            with Horizontal(id="session-actions"):
                yield Button("New session", id="new-session")
                yield Button("Resume", variant="success", id="resume-session")

    def on_mount(self) -> None:
        table = self.query_one("#session-table", DataTable)
        table.add_columns("Updated", "Session", "Source", "Events")
        for summary in self.summaries:
            updated = summary.last_event_at or summary.created_at
            updated_text = (
                updated.astimezone().strftime("%Y-%m-%d %H:%M") if updated else "-"
            )
            table.add_row(
                updated_text,
                summary.session_id,
                str(summary.source or "-"),
                str(summary.event_count),
                key=summary.session_id,
            )
        table.focus()

    @on(DataTable.RowSelected, "#session-table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        self.dismiss(str(event.row_key.value))

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-session":
            self.dismiss(None)
            return
        table = self.query_one("#session-table", DataTable)
        self.dismiss(self.summaries[table.cursor_row].session_id)

    def action_new_session(self) -> None:
        self.dismiss(None)


class TraceScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", show=False)]

    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__()
        self.report = report
        self.events_by_seq = {
            str(event["seq"]): event for event in report.get("events", [])
        }
        self.selected_event_seq: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="trace-dialog"):
            with Horizontal(id="trace-heading"):
                yield Label("Trace", id="trace-title")
                yield Button("Close", id="close-trace")
            yield Static(_trace_metrics(self.report), id="trace-metrics")
            yield DataTable(
                id="trace-events",
                cursor_type="row",
                zebra_stripes=True,
            )
            yield Label("Event payload", id="trace-payload-title")
            yield Static(id="trace-payload")

    def on_mount(self) -> None:
        table = self.query_one("#trace-events", DataTable)
        table.add_columns("Seq", "Time", "Event", "Turn", "Summary")
        for event in self.report.get("events", []):
            timestamp = str(event.get("timestamp") or "-")
            table.add_row(
                str(event.get("seq") or "-"),
                timestamp[11:19] if len(timestamp) >= 19 else timestamp,
                str(event.get("type") or "-"),
                str(event.get("turn_id") or "-"),
                str(event.get("summary") or ""),
                key=str(event["seq"]),
            )
        if table.row_count:
            table.move_cursor(row=table.row_count - 1)
            self._update_payload(str(self.report["events"][-1]["seq"]))
            table.focus()

    @on(DataTable.RowHighlighted, "#trace-events")
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_payload(str(event.row_key.value))

    @on(DataTable.RowSelected, "#trace-events")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        self._update_payload(str(event.row_key.value))

    @on(Button.Pressed, "#close-trace")
    def on_close_pressed(self) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)

    def _update_payload(self, seq: str) -> None:
        event = self.events_by_seq.get(seq)
        if event is None:
            return
        self.selected_event_seq = seq
        detail = {
            "event_id": event.get("event_id"),
            "turn_id": event.get("turn_id"),
            "timestamp": event.get("timestamp"),
            "payload": event.get("payload", {}),
        }
        serialized = json.dumps(detail, ensure_ascii=False, indent=2, sort_keys=True)
        if len(serialized) > 20_000:
            serialized = serialized[:20_000] + "\n... truncated"
        self.query_one("#trace-payload", Static).update(
            Syntax(
                serialized,
                "json",
                theme="ansi_dark",
                word_wrap=True,
                background_color="default",
            )
        )


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

    #runtime-heading {
        height: 3;
    }

    #runtime-heading .panel-title {
        width: 1fr;
        height: 3;
    }

    #open-trace {
        width: 9;
        min-width: 9;
        height: 3;
        border: none;
        background: #263138;
        color: #7bdff2;
    }

    #open-trace:focus, #open-trace:hover {
        background: #28535a;
        color: #f4f6f8;
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

    SessionBrowserScreen {
        align: center middle;
        background: #000000 55%;
    }

    #session-dialog {
        width: 96;
        max-width: 94%;
        height: 75%;
        min-height: 16;
        padding: 1 2;
        background: #181b1f;
        border: solid #4eb6c2;
    }

    #session-title {
        height: 2;
        color: #7bdff2;
        text-style: bold;
    }

    #session-table {
        height: 1fr;
        background: #14171a;
        color: #d9dde3;
    }

    #session-table > .datatable--header {
        background: #20252a;
        color: #f0c674;
        text-style: bold;
    }

    #session-table > .datatable--cursor {
        background: #28535a;
        color: #f4f6f8;
    }

    #session-actions {
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }

    #session-actions Button {
        width: 16;
        margin-left: 1;
    }

    TraceScreen {
        align: center middle;
        background: #000000 55%;
    }

    #trace-dialog {
        width: 96%;
        height: 92%;
        padding: 1 2;
        background: #181b1f;
        border: solid #4eb6c2;
    }

    #trace-heading {
        height: 3;
    }

    #trace-title {
        width: 1fr;
        height: 3;
        color: #7bdff2;
        text-style: bold;
        content-align-vertical: middle;
    }

    #close-trace {
        width: 12;
    }

    #trace-metrics {
        height: 3;
        padding: 0 1;
        background: #20252a;
    }

    #trace-events {
        height: 1fr;
        min-height: 6;
        margin-top: 1;
        background: #14171a;
        color: #d9dde3;
    }

    #trace-events > .datatable--header {
        background: #20252a;
        color: #f0c674;
        text-style: bold;
    }

    #trace-events > .datatable--cursor {
        background: #28535a;
        color: #f4f6f8;
    }

    #trace-payload-title {
        height: 2;
        padding-top: 1;
        color: #d7a95b;
        text-style: bold;
    }

    #trace-payload {
        height: 9;
        padding: 0 1;
        overflow-y: auto;
        background: #111315;
    }
    """

    def __init__(
        self,
        config: SessionConfig,
        runtime: AgentRuntime,
        *,
        runtime_factory: Callable[[SessionConfig], AgentRuntime] | None = None,
        resume_session_id: str | None = None,
        resume_last: bool = False,
        browse_sessions: bool = True,
    ) -> None:
        super().__init__()
        self.config = config
        self.runtime = runtime
        self.runtime_factory = runtime_factory
        self.resume_session_id = resume_session_id
        self.resume_last = resume_last
        self.browse_sessions = browse_sessions
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
                with Horizontal(id="runtime-heading"):
                    yield Label("Runtime", classes="panel-title")
                    yield Button("Trace", id="open-trace", disabled=True)
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
        self.run_worker(
            self._start_runtime(),
            group="runtime-startup",
            exclusive=True,
            name="runtime-startup",
        )

    async def _start_runtime(self) -> None:
        try:
            session_id = await self._select_session()
            if session_id is None:
                self.thread = await self.runtime.create_thread(self.config)
            else:
                await self._resume_session(session_id)
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
        self.query_one("#open-trace", Button).disabled = False
        self._refresh_status()
        self.run_worker(
            self._consume_events(),
            group="runtime-events",
            exclusive=True,
            name="runtime-events",
        )

    async def _select_session(self) -> str | None:
        if self.resume_session_id is not None:
            return self.resume_session_id

        summaries = await self.runtime.list_sessions(cwd=self.config.cwd)
        if self.resume_last:
            if not summaries:
                raise RuntimeError(
                    "No session found for the current working directory."
                )
            return summaries[0].session_id
        if not self.browse_sessions or not summaries:
            return None
        return await self.push_screen_wait(SessionBrowserScreen(summaries))

    async def _resume_session(self, session_id: str) -> None:
        snapshot = await self.runtime.session_store.resume(session_id)
        if self.runtime_factory is not None:
            previous_runtime = self.runtime
            self.runtime = self.runtime_factory(snapshot.config)
            await previous_runtime.close()
        elif snapshot.config != self.config:
            raise RuntimeError(
                "Resuming a session with different configuration requires a runtime factory."
            )

        self.config = snapshot.config
        self.sub_title = f"{self.config.model_provider}/{self.config.model}"
        await self._restore_history(snapshot.events)
        self.thread = await self.runtime.resume_thread(session_id)

    async def _restore_history(self, events: list[RuntimeEvent]) -> None:
        message_events = [
            event
            for event in events
            if event.type
            in {RuntimeEventType.USER_MESSAGE, RuntimeEventType.ASSISTANT_MESSAGE}
        ]
        visible_messages = message_events[-MAX_RESTORED_MESSAGES:]
        visible_message_seqs = {event.seq for event in visible_messages}
        omitted_messages = len(message_events) - len(visible_messages)
        if omitted_messages:
            await self._append_message(
                "History",
                f"{omitted_messages} earlier messages are hidden from this view.",
            )

        tool_events = [
            event
            for event in events
            if event.type == RuntimeEventType.TOOL_CALL_FINISHED
        ]
        visible_tool_seqs = {
            event.seq for event in tool_events[-MAX_RESTORED_TOOL_EVENTS:]
        }
        omitted_tools = len(tool_events) - len(visible_tool_seqs)
        if omitted_tools:
            self._tool_log().write(
                f"[dim]{omitted_tools} earlier tool results omitted[/dim]"
            )

        for event in events:
            if event.seq in visible_message_seqs:
                text = event.payload.get("text")
                if isinstance(text, str):
                    role = (
                        "User"
                        if event.type == RuntimeEventType.USER_MESSAGE
                        else "Assistant"
                    )
                    await self._append_message(role, text)
            elif event.seq in visible_tool_seqs:
                self._render_tool_finished(event.payload)
            elif event.type == RuntimeEventType.TOKEN_COUNT:
                self._accumulate_token_usage(event.payload)
        self._refresh_status()

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

    @on(Button.Pressed, "#open-trace")
    async def on_trace_pressed(self) -> None:
        try:
            events = await self.runtime.session_store.load_events(
                self.config.session_id
            )
        except CodecraftError as exc:
            self._tool_log().write(f"[red]trace unavailable: {exc.message}[/red]")
            return
        report = build_trace_report(self.config.session_id, events)
        self.push_screen(TraceScreen(report))

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
        elif event.type == RuntimeEventType.SESSION_RESTORED:
            self._tool_log().write("[cyan]session restored[/cyan]")
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
        self._accumulate_token_usage(payload)
        self._refresh_status()

    def _accumulate_token_usage(self, payload: dict[str, Any]) -> None:
        for name in self.token_usage:
            value = payload.get(name)
            if isinstance(value, int):
                self.token_usage[name] += value

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


def _trace_metrics(report: dict[str, Any]) -> Table:
    metrics = report.get("metrics", {})
    table = Table.grid(padding=(0, 1), expand=True)
    for _ in range(6):
        table.add_column(ratio=1)
    table.add_row(
        Text("events", style="#8f98a3"),
        str(metrics.get("event_count", 0)),
        Text("turns", style="#8f98a3"),
        str(metrics.get("turn_count", 0)),
        Text("tools", style="#8f98a3"),
        str(metrics.get("tool_call_count", 0)),
    )
    table.add_row(
        Text("failures", style="#8f98a3"),
        str(metrics.get("tool_failure_count", 0)),
        Text("approvals", style="#8f98a3"),
        str(metrics.get("approval_count", 0)),
        Text("status", style="#8f98a3"),
        str(metrics.get("final_status", "unknown")),
    )
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
