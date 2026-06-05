from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from codecraft.approval import ApprovalManager, ApprovalPolicy, ThreadApprovalReviewer
from codecraft.config import ConfigLoader, ConfigOverrides
from codecraft.core.ids import new_id
from codecraft.core.runtime import AgentRuntime
from codecraft.core.session_store import SessionStore
from codecraft.llm import LLMProviderRegistry, OpenAIProvider, QwenProvider
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.session import SessionConfig, SessionSource
from codecraft.tool import (
    ApplyPatchTool,
    BashTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WriteFileTool,
)

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
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Model provider: openai or qwen."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model name."),
    ] = None,
    codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Highest-priority TOML config file."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name under ~/.codecraft/profiles."),
    ] = None,
    approval_policy: Annotated[
        ApprovalPolicy | None,
        typer.Option("--approval-policy", help="Approval policy."),
    ] = None,
    network: Annotated[
        bool | None,
        typer.Option("--network/--no-network", help="Allow network commands."),
    ] = None,
) -> None:
    exit_code = asyncio.run(
        _run_exec(
            task=task,
            provider=provider,
            model=model,
            codecraft_home=codecraft_home,
            config_path=config,
            profile=profile,
            approval_policy=approval_policy,
            network=network,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command()
def chat(
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Model provider: openai or qwen."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model name."),
    ] = None,
    codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Highest-priority TOML config file."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name under ~/.codecraft/profiles."),
    ] = None,
    approval_policy: Annotated[
        ApprovalPolicy | None,
        typer.Option("--approval-policy", help="Approval policy."),
    ] = None,
    network: Annotated[
        bool | None,
        typer.Option("--network/--no-network", help="Allow network commands."),
    ] = None,
) -> None:
    exit_code = asyncio.run(
        _run_chat(
            provider=provider,
            model=model,
            codecraft_home=codecraft_home,
            config_path=config,
            profile=profile,
            approval_policy=approval_policy,
            network=network,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command()
def resume(
    last: Annotated[
        bool,
        typer.Option("--last", help="Resume the latest session."),
    ] = False,
    summary: Annotated[
        bool,
        typer.Option("--summary", help="Only print the latest session summary."),
    ] = False,
    codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
) -> None:
    if not last:
        raise typer.BadParameter("Only resume --last is available right now.")

    exit_code = asyncio.run(_run_resume_last(codecraft_home=codecraft_home, summary_only=summary))
    if exit_code:
        raise typer.Exit(code=exit_code)


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


async def _run_exec(
    *,
    task: str,
    provider: str | None,
    model: str | None,
    codecraft_home: Path,
    config_path: Path | None,
    profile: str | None,
    approval_policy: ApprovalPolicy | None,
    network: bool | None,
) -> int:
    config = _load_session_config(
        source=SessionSource.CLI_EXEC,
        provider=provider,
        model=model,
        codecraft_home=codecraft_home,
        config_path=config_path,
        profile=profile,
        approval_policy=approval_policy,
        network=network,
    )
    runtime = _build_runtime(config)
    thread = await runtime.create_thread(config)
    await thread.submit(SessionInput.user_message(new_id("inp_"), task))
    return await _consume_turn(thread)


async def _run_chat(
    *,
    provider: str | None,
    model: str | None,
    codecraft_home: Path,
    config_path: Path | None,
    profile: str | None,
    approval_policy: ApprovalPolicy | None,
    network: bool | None,
) -> int | None:
    config = _load_session_config(
        source=SessionSource.CLI_CHAT,
        provider=provider,
        model=model,
        codecraft_home=codecraft_home,
        config_path=config_path,
        profile=profile,
        approval_policy=approval_policy,
        network=network,
    )
    runtime = _build_runtime(config)
    thread = await runtime.create_thread(config)
    typer.echo(f"session_id: {config.session_id}")
    return await _interactive_loop(thread)


async def _run_resume_last(*, codecraft_home: Path, summary_only: bool) -> int:
    summary = await _latest_summary(codecraft_home)
    if summary is None:
        typer.echo("No sessions found.")
        return 1

    if summary_only:
        _print_session_summary(summary)
        return 0

    snapshot = await SessionStore(codecraft_home).resume(summary.session_id)
    runtime = _build_runtime(snapshot.config)
    thread = await runtime.resume_thread(summary.session_id)
    await _drain_restore_event(thread)
    typer.echo(f"session_id: {summary.session_id}")
    return await _interactive_loop(thread)


async def _interactive_loop(thread) -> int:
    while True:
        try:
            text = typer.prompt("codecraft").strip()
        except (EOFError, KeyboardInterrupt):
            await _shutdown_thread(thread)
            typer.echo()
            return 0

        if not text:
            continue
        if text in {"/exit", "/quit", "exit", "quit"}:
            await _shutdown_thread(thread)
            return 0

        await thread.submit(SessionInput.user_message(new_id("inp_"), text))
        exit_code = await _consume_turn(thread)
        if exit_code:
            return exit_code


async def _drain_restore_event(thread) -> None:
    event = await thread.next_event()
    if event.type != RuntimeEventType.SESSION_RESTORED:
        typer.echo(f"warning: expected session_restored, got {event.type}", err=True)


def _print_session_summary(summary) -> None:
    typer.echo(f"session_id: {summary.session_id}")
    typer.echo(f"thread_id: {summary.thread_id}")
    typer.echo(f"events: {summary.event_count}")
    typer.echo(f"file: {summary.path}")


def _load_session_config(
    *,
    source: SessionSource,
    provider: str | None,
    model: str | None,
    codecraft_home: Path,
    config_path: Path | None,
    profile: str | None,
    approval_policy: ApprovalPolicy | None,
    network: bool | None,
) -> SessionConfig:
    settings = ConfigLoader(
        cwd=Path.cwd(),
        codecraft_home=codecraft_home,
    ).load(
        profile=profile,
        config_path=config_path,
        overrides=ConfigOverrides.from_cli(
            provider=provider,
            model=model,
            approval_policy=approval_policy,
            network_access=network,
            codecraft_home=codecraft_home,
        ),
    )
    return SessionConfig(
        session_id=new_id("ses_"),
        thread_id=new_id("thr_"),
        source=source,
        cwd=Path.cwd(),
        workspace_roots=[Path.cwd()],
        codecraft_home=settings.paths.codecraft_home,
        model=settings.model.name,
        model_provider=settings.model.provider,
        approval_policy=settings.approval.policy,
        sandbox_mode=settings.sandbox.mode,
        network_access=settings.sandbox.network_access,
        user_instructions=settings.instructions.user,
    )


async def _consume_turn(thread) -> int:
    try:
        while True:
            event = await thread.next_event()
            if event.type == RuntimeEventType.ASSISTANT_MESSAGE_DELTA:
                text = event.payload.get("text")
                if isinstance(text, str):
                    typer.echo(text, nl=False)
            elif event.type == RuntimeEventType.ASSISTANT_MESSAGE:
                text = event.payload.get("text")
                if isinstance(text, str):
                    typer.echo(text)
            elif event.type == RuntimeEventType.TOOL_CALL_STARTED:
                typer.echo(_format_tool_started(event.payload))
            elif event.type == RuntimeEventType.APPROVAL_REQUESTED:
                _print_approval_request(event.payload)
                approved = typer.confirm("Approve?", default=False)
                await thread.submit(
                    SessionInput.approval_decision(
                        new_id("inp_"),
                        approval_id=str(event.payload["approval_id"]),
                        approved=approved,
                        reason="approved by CLI" if approved else "rejected by CLI",
                    )
                )
            elif event.type == RuntimeEventType.ERROR:
                typer.echo(f"error: {event.payload.get('message')}", err=True)
            elif event.type == RuntimeEventType.TURN_FINISHED:
                await thread.wait_until_idle()
                return 0
            elif event.type == RuntimeEventType.TURN_ABORTED:
                typer.echo(f"aborted: {event.payload.get('message')}", err=True)
                await thread.wait_until_idle()
                return 1
    except KeyboardInterrupt:
        await _shutdown_thread(thread)
        raise


async def _shutdown_thread(thread) -> None:
    for approval in thread.list_pending_approvals():
        await thread.submit(
            SessionInput.approval_decision(
                new_id("inp_"),
                approval_id=approval.approval_id,
                approved=False,
                reason="interrupted by CLI",
            )
        )
    await thread.interrupt("interrupted by CLI")
    await thread.close()
    try:
        await asyncio.wait_for(thread.wait_until_idle(), timeout=1)
    except TimeoutError:
        return


def _format_tool_started(payload: dict) -> str:
    name = payload.get("name")
    arguments = payload.get("arguments")
    if name == "bash" and isinstance(arguments, dict):
        command = arguments.get("command")
        if isinstance(command, str) and command:
            return f"[tool] bash: {command}"
    return f"[tool] {name}"


def _print_approval_request(payload: dict) -> None:
    tool_name = payload.get("tool_name")
    typer.echo(f"[approval] {tool_name} risk={payload.get('risk')} reason={payload.get('reason')}")
    arguments = payload.get("arguments")
    if tool_name == "bash" and isinstance(arguments, dict):
        command = arguments.get("command")
        cwd = arguments.get("cwd")
        if isinstance(command, str) and command:
            typer.echo(f"command: {command}")
        if isinstance(cwd, str) and cwd:
            typer.echo(f"cwd: {cwd}")


def _build_runtime(config: SessionConfig) -> AgentRuntime:
    return AgentRuntime(
        session_store=SessionStore(config.codecraft_home),
        llm_providers=_build_provider_registry(),
        tool_registry=_build_tool_registry(),
        approval_manager=ApprovalManager(
            policy=ApprovalPolicy(config.approval_policy),
            reviewer=ThreadApprovalReviewer(),
        ),
    )


def _build_provider_registry() -> LLMProviderRegistry:
    return LLMProviderRegistry([OpenAIProvider(), QwenProvider()])


def _build_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ReadFileTool(),
            ListFilesTool(),
            WriteFileTool(),
            ApplyPatchTool(),
            BashTool(),
        ]
    )


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
