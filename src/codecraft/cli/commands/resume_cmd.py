from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codecraft.cli.commands.common import build_shell_context
from codecraft.cli.options import CodecraftHomeOption
from codecraft.cli.shell import InteractiveShell
from codecraft.cli.ui import make_console
from codecraft.cli.ui.session_renderer import SessionRenderer
from codecraft.core.errors import SessionRestoreError
from codecraft.core.session_store import SessionStore
from codecraft.schema.event import RuntimeEventType


def register_resume_command(app: typer.Typer) -> None:
    @app.command("resume")
    def resume_command(
        session_id: Annotated[
            str | None,
            typer.Argument(help="Session id to resume."),
        ] = None,
        last: Annotated[
            bool,
            typer.Option("--last", help="Resume the latest session."),
        ] = False,
        summary: Annotated[
            bool,
            typer.Option("--summary", help="Only print the session summary."),
        ] = False,
        codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
        debug: Annotated[
            bool,
            typer.Option("--debug", help="Show verbose runtime events."),
        ] = False,
    ) -> None:
        import asyncio

        exit_code = asyncio.run(
            run_resume(
                session_id=session_id,
                last=last,
                summary_only=summary,
                codecraft_home=codecraft_home,
                debug=debug,
            )
        )
        if exit_code:
            raise typer.Exit(code=exit_code)


async def run_resume(
    *,
    session_id: str | None,
    last: bool,
    summary_only: bool,
    codecraft_home: Path,
    debug: bool = False,
) -> int:
    store = SessionStore(codecraft_home)
    if session_id is None:
        if not last:
            raise typer.BadParameter("Use resume --last or resume <session_id>.")
        latest = await latest_summary(codecraft_home)
        if latest is None:
            make_console().print("No sessions found.")
            return 1
        session_id = latest.session_id

    summaries = await store.list_sessions(include_invalid=True)
    summary = next((item for item in summaries if item.session_id == session_id), None)
    if summary_only:
        if summary is None:
            make_console().print(f"No session found: {session_id}")
            return 1
        SessionRenderer(make_console()).render_summary(summary)
        return 0

    if summary is None:
        make_console().print(f"No session found: {session_id}")
        return 1

    try:
        snapshot = await store.resume(session_id)
    except SessionRestoreError as exc:
        make_console().print(
            f"Could not resume session {session_id}: {exc.message} ({exc.code})",
            markup=False,
            soft_wrap=True,
        )
        return 1
    from codecraft.cli import app as cli_app

    runtime = cli_app._build_runtime(snapshot.config)
    thread = await runtime.resume_thread(session_id)
    event = await thread.next_event()
    if event.type != RuntimeEventType.SESSION_RESTORED:
        make_console(stderr=True).print(
            f"warning: expected session_restored, got {event.type}"
        )

    context, input_controller = build_shell_context(
        runtime=runtime,
        thread=thread,
        config=snapshot.config,
        debug=debug,
    )
    if summary is not None:
        SessionRenderer(context.console).render_resumed(summary)
    return await InteractiveShell(context, input_controller).run(show_welcome=False)


async def latest_summary(codecraft_home: Path):
    summaries = await SessionStore(codecraft_home).list_sessions()
    return summaries[0] if summaries else None
