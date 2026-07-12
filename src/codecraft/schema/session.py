from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from codecraft.approval.policy import ApprovalPolicy
from codecraft.mcp.config import MCPServerSettings
from codecraft.sandbox import DockerSandboxConfig, SandboxBackendType, SandboxMode
from codecraft.schema.event import RuntimeEvent


class SessionSource(StrEnum):
    CLI_CHAT = "cli_chat"
    CLI_EXEC = "cli_exec"
    CLI_EVAL = "cli_eval"
    RESUME = "resume"
    TEST = "test"


class SessionConfig(BaseModel):
    """启动或恢复 session 所需的完整运行配置。"""

    session_id: str
    thread_id: str
    source: SessionSource

    cwd: Path
    workspace_roots: list[Path]
    codecraft_home: Path

    model: str
    model_provider: str
    model_api_key_env: str | None = None
    model_base_url: str | None = None

    approval_policy: ApprovalPolicy
    sandbox_mode: SandboxMode
    network_access: bool = False
    sandbox_backend: SandboxBackendType = SandboxBackendType.LOCAL
    docker_sandbox: DockerSandboxConfig = Field(default_factory=DockerSandboxConfig)
    mcp_servers: dict[str, MCPServerSettings] = Field(default_factory=dict)

    base_instructions: str | None = None
    project_instructions: str | None = None
    user_instructions: str | None = None

    max_turn_steps: int = 30
    max_tool_output_chars: int = 80_000
    max_conversation_items: int = 200

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError("cwd must be an existing directory")
        return resolved

    @field_validator("codecraft_home")
    @classmethod
    def normalize_codecraft_home(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("workspace_roots")
    @classmethod
    def validate_workspace_roots(cls, value: list[Path]) -> list[Path]:
        if not value:
            raise ValueError("workspace_roots must include at least one directory")

        roots = [path.expanduser().resolve() for path in value]
        missing = [path for path in roots if not path.exists() or not path.is_dir()]
        if missing:
            raise ValueError(f"workspace_roots must be directories: {missing}")

        return roots

    @model_validator(mode="after")
    def validate_runtime_names(self) -> SessionConfig:
        if not self.model_provider:
            raise ValueError("model_provider must not be empty")

        return self


class SessionSummary(BaseModel):
    """用于列表页/命令输出的轻量 session 信息。"""

    session_id: str
    thread_id: str
    path: Path
    valid: bool = True
    error_code: str | None = None
    error_message: str | None = None
    cwd: Path | None = None
    source: SessionSource | None = None
    created_at: datetime | None = None
    last_event_at: datetime | None = None
    event_count: int = 0


class SessionSnapshot(BaseModel):
    """恢复 session 时读取到的配置和事件日志。"""

    config: SessionConfig
    events: list[RuntimeEvent]
