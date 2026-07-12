from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codecraft.approval import ApprovalPolicy
from codecraft.cli.options import CodecraftHomeOption
from codecraft.schema.session import SessionSource
from codecraft.tui import CodeCraftTUI


def register_tui_command(app: typer.Typer) -> None:
    @app.command("tui")
    def tui_command(
        provider: Annotated[
            str | None,
            typer.Option(
                "--provider", help="Model provider: openai, qwen, or deepseek."
            ),
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
        from codecraft.cli import app as cli_app

        session_config = cli_app._load_session_config(
            source=SessionSource.CLI_TUI,
            provider=provider,
            model=model,
            codecraft_home=codecraft_home,
            config_path=config,
            profile=profile,
            approval_policy=approval_policy,
            network=network,
        )
        CodeCraftTUI(
            session_config,
            cli_app._build_runtime(session_config),
        ).run()
