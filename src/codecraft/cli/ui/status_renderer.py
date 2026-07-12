from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codecraft.schema.session import SessionConfig
from codecraft.tool.registry import ToolRegistry


class StatusRenderer:
    def __init__(self, console: Console) -> None:
        self.console = console

    def render_status(self, config: SessionConfig) -> None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="muted")
        table.add_column()
        table.add_row("session", config.session_id)
        table.add_row("thread", config.thread_id)
        table.add_row("cwd", str(config.cwd))
        table.add_row("model", config.model)
        table.add_row("provider", config.model_provider)
        table.add_row("approval", config.approval_policy)
        table.add_row("sandbox", config.sandbox_mode)
        table.add_row("sandbox backend", config.sandbox_backend)
        table.add_row("mcp servers", str(len(config.mcp_servers)))
        table.add_row("network", "enabled" if config.network_access else "disabled")
        self.console.print(Panel(table, title="session status", border_style="cyan"))

    def render_tools(self, registry: ToolRegistry) -> None:
        table = Table(title="Registered Tools")
        table.add_column("Name")
        table.add_column("Description")
        for tool in registry.list():
            table.add_row(tool.name, tool.description)
        self.console.print(table)

    def render_model(self, config: SessionConfig) -> None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="muted")
        table.add_column()
        table.add_row("provider", config.model_provider)
        table.add_row("model", config.model)
        table.add_row("base_url", config.model_base_url or "-")
        table.add_row("api_key_env", config.model_api_key_env or "-")
        self.console.print(Panel(table, title="model", border_style="cyan"))
