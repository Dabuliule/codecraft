from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codecraft.cli.options import CodecraftHomeOption
from codecraft.cli.ui import make_console
from codecraft.cli.ui.session_renderer import SessionRenderer, last_answer
from codecraft.core.session_store import SessionStore
from codecraft.schema.event import RuntimeEvent, RuntimeEventType


def register_inspect_command(app: typer.Typer) -> None:
    @app.command("inspect")
    def inspect_command(
        session_id: Annotated[str, typer.Argument(help="Session id to inspect.")],
        codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
        events: Annotated[
            bool,
            typer.Option("--events", help="Print every event."),
        ] = False,
        tools: Annotated[
            bool,
            typer.Option("--tools", help="Print tool call summaries."),
        ] = False,
        errors: Annotated[
            bool,
            typer.Option("--errors", help="Print error and aborted events."),
        ] = False,
        raw: Annotated[
            bool,
            typer.Option("--raw", help="Print raw JSONL lines without validation."),
        ] = False,
    ) -> None:
        import asyncio

        asyncio.run(
            run_inspect(
                session_id=session_id,
                codecraft_home=codecraft_home,
                events=events,
                tools=tools,
                errors=errors,
                raw=raw,
            )
        )


async def run_inspect(
    *,
    session_id: str,
    codecraft_home: Path,
    events: bool,
    tools: bool,
    errors: bool,
    raw: bool,
) -> None:
    console = make_console()
    store = SessionStore(codecraft_home)
    if raw:
        lines = await store.load_raw_lines(session_id)
        console.print(f"session_id: {session_id}", soft_wrap=True)
        console.print(f"raw_lines: {len(lines)}", soft_wrap=True)
        for line_number, line in enumerate(lines, start=1):
            console.print(f"{line_number}: {line}", soft_wrap=True, markup=False)
        return

    loaded = await store.load_events(session_id)
    renderer = SessionRenderer(console)
    renderer.render_inspect_summary(session_id, loaded)

    console.print(f"session_id: {session_id}", style="muted")
    console.print(f"events: {len(loaded)}", style="muted")
    if loaded:
        console.print(f"last_event: {loaded[-1].type}", style="muted")

    answer = last_answer(loaded)
    if answer:
        console.print(f"final_answer: {answer}", style="muted")

    if events:
        renderer.render_events(loaded)
        print_event_compat_lines(console, loaded)
    if tools:
        renderer.render_tool_events(loaded)
        print_tool_compat_lines(console, loaded)
    if errors:
        renderer.render_error_events(loaded)
        print_error_compat_lines(console, loaded)


def print_event_compat_lines(console, events: list[RuntimeEvent]) -> None:
    for event in events:
        console.print(
            f"{event.seq} {event.type} turn={event.turn_id or '-'} payload={event.payload}",
            style="muted",
            soft_wrap=True,
            markup=False,
        )


def print_tool_compat_lines(console, events: list[RuntimeEvent]) -> None:
    for event in events:
        if event.type == RuntimeEventType.MODEL_TOOL_CALL:
            console.print(
                f"{event.seq} model_tool_call {event.payload.get('name')} "
                f"args={event.payload.get('arguments')}",
                style="muted",
                soft_wrap=True,
                markup=False,
            )
        elif event.type == RuntimeEventType.TOOL_CALL_STARTED:
            console.print(
                f"{event.seq} {format_tool_started(event.payload)}",
                style="muted",
                soft_wrap=True,
                markup=False,
            )
        elif event.type == RuntimeEventType.TOOL_CALL_FINISHED:
            console.print(
                f"{event.seq} {format_tool_finished(event.payload)}",
                style="muted",
                soft_wrap=True,
                markup=False,
            )


def print_error_compat_lines(console, events: list[RuntimeEvent]) -> None:
    for event in events:
        if event.type == RuntimeEventType.ERROR:
            console.print(
                f"{event.seq} error turn={event.turn_id or '-'} payload={event.payload}",
                style="muted",
                soft_wrap=True,
                markup=False,
            )
        elif event.type == RuntimeEventType.TURN_ABORTED:
            console.print(
                f"{event.seq} aborted turn={event.turn_id or '-'} payload={event.payload}",
                style="muted",
                soft_wrap=True,
                markup=False,
            )
        elif event.type == RuntimeEventType.TOOL_CALL_FINISHED:
            result = event.payload.get("result")
            if isinstance(result, dict) and result.get("success") is False:
                console.print(
                    f"{event.seq} tool_error {event.payload.get('name')} payload={result}",
                    style="muted",
                    soft_wrap=True,
                    markup=False,
                )


def format_tool_started(payload: dict) -> str:
    name = payload.get("name")
    arguments = payload.get("arguments")
    if name == "bash" and isinstance(arguments, dict):
        command = arguments.get("command")
        if isinstance(command, str) and command:
            return f"[tool] bash: {command}"
    return f"[tool] {name}"


def format_tool_finished(payload: dict) -> str:
    name = payload.get("name")
    result = payload.get("result")
    duration_ms = payload.get("duration_ms")
    if not isinstance(result, dict):
        return f"[tool] {name} finished"

    status = "ok" if result.get("success") is True else "failed"
    content = preview(str(result.get("content") or result.get("error") or ""))
    duration = f" ({duration_ms}ms)" if isinstance(duration_ms, int) else ""
    return f"[tool] {name} {status}{duration}: {content}"


def preview(value: str, *, max_chars: int = 160) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."
