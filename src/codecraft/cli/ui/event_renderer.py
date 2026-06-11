from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from codecraft.cli.ui.approval_renderer import ApprovalRenderer
from codecraft.cli.ui.error_renderer import ErrorRenderer
from codecraft.cli.ui.render_config import RenderConfig
from codecraft.cli.ui.session_renderer import SessionRenderer
from codecraft.cli.ui.tool_renderer import ToolRenderer
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.session import SessionConfig


class RuntimeEventRenderer:
    def __init__(
        self,
        *,
        console: Console,
        render_config: RenderConfig | None = None,
        tool_renderer: ToolRenderer | None = None,
        approval_renderer: ApprovalRenderer | None = None,
        error_renderer: ErrorRenderer | None = None,
        session_renderer: SessionRenderer | None = None,
    ) -> None:
        self.console = console
        self.render_config = render_config or RenderConfig()
        self.tool_renderer = tool_renderer or ToolRenderer(console, self.render_config)
        self.approval_renderer = approval_renderer or ApprovalRenderer(console)
        self.error_renderer = error_renderer or ErrorRenderer(console)
        self.session_renderer = session_renderer or SessionRenderer(console)
        self._streaming = False
        self._stream_buffer: list[str] = []
        self._stream_live: Live | None = None

    def render_welcome(self, config: SessionConfig) -> None:
        self.session_renderer.render_welcome(config)

    async def render(self, event: RuntimeEvent) -> None:
        if event.type == RuntimeEventType.ASSISTANT_MESSAGE_DELTA:
            text = event.payload.get("text")
            if isinstance(text, str):
                self._streaming = True
                self._stream_buffer.append(text)
                self._render_stream()
        elif event.type == RuntimeEventType.ASSISTANT_MESSAGE:
            text = event.payload.get("text")
            if isinstance(text, str):
                if self._streaming:
                    self._finish_stream(text)
                else:
                    self._render_markdown(text)
        elif event.type == RuntimeEventType.TOOL_CALL_STARTED:
            self.ensure_newline()
            self.tool_renderer.render_started(event.payload)
        elif event.type == RuntimeEventType.TOOL_CALL_FINISHED:
            self.ensure_newline()
            self.tool_renderer.render_finished(event.payload)
        elif event.type == RuntimeEventType.APPROVAL_DECIDED:
            self.ensure_newline()
            approved = event.payload.get("approved")
            style = "success" if approved else "warning"
            label = "approved" if approved else "rejected"
            self.console.print(f"[{style}]approval {label}[/{style}]")
        elif event.type == RuntimeEventType.PATCH_APPLIED:
            self.ensure_newline()
            self.tool_renderer.render_patch_applied(event.payload)
        elif event.type == RuntimeEventType.TOKEN_COUNT and self.render_config.show_token_usage:
            if self.render_config.debug:
                self.console.print(f"[muted]tokens {event.payload}[/muted]")
        elif event.type == RuntimeEventType.CONTEXT_COMPACTED:
            self.ensure_newline()
            self.console.print("[warning]context compacted[/warning]")
        elif event.type == RuntimeEventType.ERROR:
            self.ensure_newline()
            self.error_renderer.render_error(event.payload)
        elif event.type == RuntimeEventType.TURN_ABORTED:
            self.ensure_newline()
            self.error_renderer.render_aborted(event.payload)
        elif event.type == RuntimeEventType.SESSION_RESTORED:
            if self.render_config.debug:
                self.console.print("[muted]session restored[/muted]")
        elif event.type in {
            RuntimeEventType.SESSION_STARTED,
            RuntimeEventType.SESSION_CONFIGURED,
            RuntimeEventType.TURN_STARTED,
            RuntimeEventType.USER_MESSAGE,
            RuntimeEventType.MODEL_TOOL_CALL,
            RuntimeEventType.TURN_FINISHED,
            RuntimeEventType.SESSION_CLOSED,
        }:
            if self.render_config.debug:
                self.console.print(f"[muted]{event.type} {event.payload}[/muted]")

    async def request_approval(self, event: RuntimeEvent) -> SessionInput:
        self.ensure_newline()
        return await self.approval_renderer.request_decision(event)

    def render_unknown_slash_command(self, name: str) -> None:
        self.console.print(f"[warning]unknown command:[/warning] /{name}")

    def ensure_newline(self) -> None:
        if self._streaming:
            text = "".join(self._stream_buffer)
            self._finish_stream(text)

    def _render_stream(self) -> None:
        if not self.console.is_terminal:
            return

        text = "".join(self._stream_buffer)
        renderable = Markdown(text)
        if self._stream_live is None:
            self._stream_live = Live(
                renderable,
                console=self.console,
                refresh_per_second=12,
                transient=False,
            )
            self._stream_live.start()
        else:
            self._stream_live.update(renderable, refresh=True)

    def _finish_stream(self, text: str) -> None:
        if self._stream_live is not None:
            self._stream_live.update(Markdown(text), refresh=True)
            self._stream_live.stop()
            self._stream_live = None
        elif text:
            self._render_markdown(text)

        self._streaming = False
        self._stream_buffer.clear()

    def _render_markdown(self, text: str) -> None:
        self.console.print(Markdown(text))
