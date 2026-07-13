from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codecraft.cli.options import CodecraftHomeOption
from codecraft.cli.ui import make_console
from codecraft.cli.ui.session_renderer import SessionRenderer
from codecraft.core.session_store import SessionStore


def register_sessions_command(app: typer.Typer) -> None:
    @app.command("sessions")
    def sessions_command(
        codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
        all_sessions: Annotated[
            bool,
            typer.Option("--all", help="Include invalid session logs."),
        ] = False,
    ) -> None:
        import asyncio

        asyncio.run(
            run_sessions(codecraft_home=codecraft_home, all_sessions=all_sessions)
        )


async def run_sessions(*, codecraft_home: Path, all_sessions: bool) -> None:
    summaries = await SessionStore(codecraft_home).list_sessions(
        include_invalid=all_sessions
    )
    console = make_console()
    if not summaries:
        console.print("No sessions found.")
        return

    SessionRenderer(console).render_sessions(summaries)
