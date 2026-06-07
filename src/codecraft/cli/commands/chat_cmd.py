from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codecraft.approval import ApprovalPolicy
from codecraft.cli.commands.common import build_shell_context
from codecraft.cli.options import CodecraftHomeOption
from codecraft.cli.shell import InteractiveShell
from codecraft.schema.session import SessionSource


def register_chat_command(app: typer.Typer) -> None:
    @app.command("chat")
    def chat_command(
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
        debug: Annotated[
            bool,
            typer.Option("--debug", help="Show verbose runtime events."),
        ] = False,
    ) -> None:
        import asyncio

        exit_code = asyncio.run(
            run_chat(
                provider=provider,
                model=model,
                codecraft_home=codecraft_home,
                config_path=config,
                profile=profile,
                approval_policy=approval_policy,
                network=network,
                debug=debug,
            )
        )
        if exit_code:
            raise typer.Exit(code=exit_code)


async def run_chat(
    *,
    provider: str | None,
    model: str | None,
    codecraft_home: Path,
    config_path: Path | None,
    profile: str | None,
    approval_policy: ApprovalPolicy | None,
    network: bool | None,
    initial_prompt: str | None = None,
    debug: bool = False,
) -> int:
    from codecraft.cli import app as cli_app

    config = cli_app._load_session_config(
        source=SessionSource.CLI_CHAT,
        provider=provider,
        model=model,
        codecraft_home=codecraft_home,
        config_path=config_path,
        profile=profile,
        approval_policy=approval_policy,
        network=network,
    )
    runtime = cli_app._build_runtime(config)
    thread = await runtime.create_thread(config)
    context, input_controller = build_shell_context(
        runtime=runtime,
        thread=thread,
        config=config,
        debug=debug,
    )
    return await InteractiveShell(context, input_controller).run(initial_prompt)
