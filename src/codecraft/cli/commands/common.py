from __future__ import annotations

from pathlib import Path

from codecraft.cli.shell import ShellContext, build_default_router
from codecraft.cli.shell.input_controller import InputController
from codecraft.cli.ui import RenderConfig, RuntimeEventRenderer, make_console
from codecraft.cli.ui.approval_renderer import ApprovalRenderer
from codecraft.core.runtime import AgentRuntime
from codecraft.core.thread import AgentThread
from codecraft.schema.session import SessionConfig


def build_shell_context(
    *,
    runtime: AgentRuntime,
    thread: AgentThread,
    config: SessionConfig,
    debug: bool = False,
) -> tuple[ShellContext, InputController]:
    console = make_console()
    input_controller = InputController(config.codecraft_home / "history")
    render_config = RenderConfig(debug=debug)
    approval_renderer = ApprovalRenderer(console, ask=input_controller.ask)
    renderer = RuntimeEventRenderer(
        console=console,
        render_config=render_config,
        approval_renderer=approval_renderer,
    )
    context = ShellContext(
        runtime=runtime,
        thread=thread,
        config=config,
        console=console,
        renderer=renderer,
        slash_router=build_default_router(),
    )
    return context, input_controller


def resolve_home(path: Path) -> Path:
    return path.expanduser().resolve()
