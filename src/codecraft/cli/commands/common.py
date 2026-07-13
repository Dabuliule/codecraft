from __future__ import annotations

from codecraft.cli.ui import RenderConfig, RuntimeEventRenderer, make_console
from codecraft.core.errors import CodecraftError


def build_event_renderer(*, debug: bool = False) -> RuntimeEventRenderer:
    console = make_console()
    return RuntimeEventRenderer(
        console=console,
        render_config=RenderConfig(debug=debug),
    )


def render_startup_error(error: CodecraftError) -> None:
    console = make_console(stderr=True)
    console.print(f"{error.message} ({error.code})", style="error", markup=False)
    if error.suggestion:
        console.print(error.suggestion, style="muted", markup=False, soft_wrap=True)
