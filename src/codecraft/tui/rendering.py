from __future__ import annotations

from rich.table import Table
from rich.text import Text

from codecraft.schema.session import SessionConfig


def runtime_status(
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
