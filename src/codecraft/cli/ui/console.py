from __future__ import annotations

from rich.console import Console
from rich.theme import Theme


CODECRAFT_THEME = Theme(
    {
        "title": "bold",
        "user": "bold cyan",
        "assistant": "default",
        "tool": "magenta",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "muted": "dim",
        "path": "cyan",
        "command": "yellow",
        "approval": "bold yellow",
    }
)


def make_console(*, stderr: bool = False) -> Console:
    return Console(theme=CODECRAFT_THEME, stderr=stderr)
