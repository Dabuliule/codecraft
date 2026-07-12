from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from typer.core import TyperGroup

from codecraft.approval import ApprovalPolicy
from codecraft.cli import bootstrap
from codecraft.cli.commands import (
    register_chat_command,
    register_eval_command,
    register_exec_command,
    register_index_command,
    register_inspect_command,
    register_retrieval_eval_command,
    register_resume_command,
    register_sessions_command,
    register_trace_command,
    run_chat,
)
from codecraft.cli.options import CodecraftHomeOption
from codecraft.core.runtime import AgentRuntime
from codecraft.llm import LLMProviderRegistry
from codecraft.schema.session import SessionConfig, SessionSource
from codecraft.tool import ToolRegistry


class CodeCraftTyperGroup(TyperGroup):
    def parse_args(self, ctx, args):
        rest = super().parse_args(ctx, args)
        protected = list(getattr(ctx, "_protected_args", []))
        if protected and self.get_command(ctx, protected[0]) is None:
            ctx.args = protected + list(ctx.args)
            ctx._protected_args = []
        return rest


app = typer.Typer(
    cls=CodeCraftTyperGroup,
    no_args_is_help=False,
    invoke_without_command=True,
    help="CodeCraft local coding agent.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@app.callback()
def main(
    ctx: typer.Context,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Model provider: openai, qwen, or deepseek."),
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
    if ctx.invoked_subcommand is not None:
        return
    initial_task = " ".join(ctx.args).strip() or None
    exit_code = asyncio.run(
        run_chat(
            provider=provider,
            model=model,
            codecraft_home=codecraft_home,
            config_path=config,
            profile=profile,
            approval_policy=approval_policy,
            network=network,
            initial_prompt=initial_task,
            debug=debug,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


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
    return bootstrap.load_session_config(
        source=source,
        provider=provider,
        model=model,
        codecraft_home=codecraft_home,
        config_path=config_path,
        profile=profile,
        approval_policy=approval_policy,
        network=network,
    )


def _build_runtime(config: SessionConfig) -> AgentRuntime:
    return bootstrap.build_runtime(
        config,
        llm_providers=_build_provider_registry(config),
        tool_registry=_build_tool_registry(config),
    )


def _build_provider_registry(config: SessionConfig) -> LLMProviderRegistry:
    return bootstrap.build_provider_registry(config)


def _provider_api_key_env(config: SessionConfig, provider: str) -> str | None:
    return bootstrap.provider_api_key_env(config, provider)


def _model_api_key_env(provider: str, configured: str | None) -> str | None:
    return bootstrap.model_api_key_env(provider, configured)


def _build_tool_registry(config: SessionConfig | None = None) -> ToolRegistry:
    return bootstrap.build_tool_registry(config)


register_exec_command(app)
register_chat_command(app)
register_eval_command(app)
register_index_command(app)
register_retrieval_eval_command(app)
register_resume_command(app)
register_sessions_command(app)
register_inspect_command(app)
register_trace_command(app)


if __name__ == "__main__":
    app()
