from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from codecraft.approval import ApprovalManager, ApprovalPolicy
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
    config = SessionConfig(
        session_id=new_id("ses_"),
        thread_id=new_id("thr_"),
        source=SessionSource.CLI_EXEC,
        cwd=Path.cwd(),
        workspace_roots=[Path.cwd()],
        codecraft_home=settings.paths.codecraft_home,
        model=settings.model.name,
        model_provider=settings.model.provider,
        approval_policy=settings.approval.policy,
        sandbox_mode=settings.sandbox.mode,
        network_access=settings.sandbox.network_access,
    )
    runtime = _build_runtime(config)
    thread = await runtime.create_thread(config)
    await thread.submit(SessionInput.user_message(new_id("inp_"), task))

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
            typer.echo(f"[tool] {event.payload.get('name')}")
        elif event.type == RuntimeEventType.APPROVAL_REQUESTED:
            approved = typer.confirm(
                f"Approve {event.payload.get('tool_name')}? {event.payload.get('reason')}",
                default=False,
            )
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


def _build_runtime(config: SessionConfig) -> AgentRuntime:
    return AgentRuntime(
        session_store=SessionStore(config.codecraft_home),
        llm_providers=_build_provider_registry(),
        tool_registry=_build_tool_registry(),
        approval_manager=ApprovalManager(
            policy=ApprovalPolicy(config.approval_policy),
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
