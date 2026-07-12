from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from codecraft.approval.policy import ApprovalPolicy
from codecraft.sandbox import DockerSandboxConfig, SandboxBackendType, SandboxMode


class ModelSettings(BaseModel):
    provider: str = "qwen"
    name: str = "qwen-plus"
    api_key_env: str | None = None
    base_url: str | None = None


class ApprovalSettings(BaseModel):
    policy: ApprovalPolicy = ApprovalPolicy.ON_REQUEST


class SandboxSettings(BaseModel):
    mode: SandboxMode = SandboxMode.WORKSPACE_WRITE
    network_access: bool = False
    backend: SandboxBackendType = SandboxBackendType.LOCAL
    docker: DockerSandboxConfig = Field(default_factory=DockerSandboxConfig)


class PathsSettings(BaseModel):
    codecraft_home: Path = Path("~/.codecraft")
    sessions_dir: Path | None = None

    @field_validator("codecraft_home", "sessions_dir")
    @classmethod
    def expand_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value.expanduser()


class InstructionSettings(BaseModel):
    user: str | None = None


class RuntimeSettings(BaseModel):
    model: ModelSettings = Field(default_factory=ModelSettings)
    approval: ApprovalSettings = Field(default_factory=ApprovalSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    instructions: InstructionSettings = Field(default_factory=InstructionSettings)
