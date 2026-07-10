from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecraft.approval import ApprovalManager, ApprovalPolicy, ThreadApprovalReviewer
from codecraft.config import ConfigLoader, ConfigOverrides
from codecraft.core.ids import new_id
from codecraft.core.runtime import AgentRuntime
from codecraft.core.session_store import SessionStore
from codecraft.llm import (
    DeepSeekProvider,
    LLMProviderRegistry,
    OpenAIProvider,
    QwenProvider,
)
from codecraft.schema.session import SessionConfig, SessionSource
from codecraft.tool import (
    ApplyPatchTool,
    BashTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WorkspaceSearchTool,
    WriteFileTool,
)


@dataclass(frozen=True)
class RuntimeBootstrapResult:
    config: SessionConfig
    runtime: AgentRuntime


def bootstrap_runtime(
    *,
    source: SessionSource,
    provider: str | None,
    model: str | None,
    codecraft_home: Path,
    config_path: Path | None,
    profile: str | None,
    approval_policy: ApprovalPolicy | None,
    network: bool | None,
) -> RuntimeBootstrapResult:
    config = load_session_config(
        source=source,
        provider=provider,
        model=model,
        codecraft_home=codecraft_home,
        config_path=config_path,
        profile=profile,
        approval_policy=approval_policy,
        network=network,
    )
    return RuntimeBootstrapResult(config=config, runtime=build_runtime(config))


def load_session_config(
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
        model_api_key_env=model_api_key_env(
            settings.model.provider, settings.model.api_key_env
        ),
        model_base_url=settings.model.base_url,
        approval_policy=settings.approval.policy,
        sandbox_mode=settings.sandbox.mode,
        network_access=settings.sandbox.network_access,
        user_instructions=settings.instructions.user,
    )


def build_runtime(
    config: SessionConfig,
    *,
    llm_providers: LLMProviderRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AgentRuntime:
    return AgentRuntime(
        session_store=SessionStore(config.codecraft_home),
        llm_providers=llm_providers or build_provider_registry(config),
        tool_registry=tool_registry or build_tool_registry(),
        approval_manager=ApprovalManager(
            policy=config.approval_policy,
            reviewer=ThreadApprovalReviewer(),
        ),
    )


def build_provider_registry(config: SessionConfig) -> LLMProviderRegistry:
    return LLMProviderRegistry(
        [
            OpenAIProvider(
                api_key_env=provider_api_key_env(config, "openai"),
                base_url=config.model_base_url,
            ),
            QwenProvider(
                api_key_env=provider_api_key_env(config, "qwen"),
                base_url=config.model_base_url,
            ),
            DeepSeekProvider(
                api_key_env=provider_api_key_env(config, "deepseek"),
                base_url=config.model_base_url,
            ),
        ]
    )


def provider_api_key_env(config: SessionConfig, provider: str) -> str | None:
    configured = config.model_api_key_env if config.model_provider == provider else None
    return model_api_key_env(provider, configured)


def model_api_key_env(provider: str, configured: str | None) -> str | None:
    if configured:
        return configured
    if provider == "qwen":
        return "DASHSCOPE_API_KEY"
    if provider == "openai":
        return "OPENAI_API_KEY"
    if provider == "deepseek":
        return "DEEPSEEK_API_KEY"
    return None


def build_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ReadFileTool(),
            ListFilesTool(),
            WorkspaceSearchTool(),
            WriteFileTool(),
            ApplyPatchTool(),
            BashTool(),
        ]
    )
