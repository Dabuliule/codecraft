from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from codecraft.core.session_store import SessionStore
from codecraft.schema.event import RuntimeEvent, RuntimeEventType

app = typer.Typer(no_args_is_help=True)


CodecraftHomeOption = Annotated[
    Path,
    typer.Option(
        "--codecraft-home",
        help="Directory containing Codecraft runtime state.",
    ),
]


@app.command()
def exec(
    task: Annotated[str, typer.Argument(help="User task to submit to Codecraft.")],
) -> None:
    raise typer.BadParameter(
        "codecraft exec will be connected after a real LLM provider lands."
    )


@app.command()
def chat() -> None:
    raise typer.BadParameter(
        "codecraft chat will be connected after a real LLM provider lands."
    )


@app.command()
def resume(
    last: Annotated[
        bool,
        typer.Option("--last", help="Show the latest resumable session."),
    ] = False,
    codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
) -> None:
    if not last:
        raise typer.BadParameter("Only resume --last is available right now.")

    summary = asyncio.run(_latest_summary(codecraft_home))
    if summary is None:
        typer.echo("No sessions found.")
        raise typer.Exit(code=1)

    typer.echo(f"session_id: {summary.session_id}")
    typer.echo(f"thread_id: {summary.thread_id}")
    typer.echo(f"events: {summary.event_count}")
    typer.echo(f"file: {summary.path}")


@app.command()
def sessions(
    codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
) -> None:
    summaries = asyncio.run(SessionStore(codecraft_home).list_sessions())
    if not summaries:
        typer.echo("No sessions found.")
        return

    for summary in summaries:
        typer.echo(
            " ".join(
                [
                    summary.session_id,
                    f"thread={summary.thread_id or '-'}",
                    f"events={summary.event_count}",
                    f"cwd={summary.cwd or '-'}",
                ]
            )
        )


@app.command()
def inspect(
    session_id: Annotated[str, typer.Argument(help="Session id to inspect.")],
    codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
    events: Annotated[
        bool,
        typer.Option("--events", help="Print every event."),
    ] = False,
) -> None:
    loaded = asyncio.run(_load_events(codecraft_home, session_id))
    typer.echo(f"session_id: {session_id}")
    typer.echo(f"events: {len(loaded)}")
    if loaded:
        typer.echo(f"last_event: {loaded[-1].type}")

    answer = _last_answer(loaded)
    if answer:
        typer.echo(f"final_answer: {answer}")

    if events:
        for event in loaded:
            typer.echo(
                f"{event.seq} {event.type} turn={event.turn_id or '-'} payload={event.payload}"
            )


async def _latest_summary(codecraft_home: Path):
    summaries = await SessionStore(codecraft_home).list_sessions()
    return summaries[0] if summaries else None


async def _load_events(codecraft_home: Path, session_id: str) -> list[RuntimeEvent]:
    return await SessionStore(codecraft_home).load_events(session_id)


def _last_answer(events: list[RuntimeEvent]) -> str | None:
    for event in reversed(events):
        if event.type == RuntimeEventType.TURN_FINISHED:
            answer = event.payload.get("answer")
            if isinstance(answer, str):
                return answer
    return None


if __name__ == "__main__":
    app()
