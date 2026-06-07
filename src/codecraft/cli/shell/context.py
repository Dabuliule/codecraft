from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console

from codecraft.core.runtime import AgentRuntime
from codecraft.core.thread import AgentThread
from codecraft.schema.session import SessionConfig
from codecraft.cli.shell.slash_command import SlashCommandRouter
from codecraft.cli.ui.event_renderer import RuntimeEventRenderer


@dataclass
class ShellContext:
    runtime: AgentRuntime
    thread: AgentThread
    config: SessionConfig
    console: Console
    renderer: RuntimeEventRenderer
    slash_router: SlashCommandRouter
