from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class ModelSettings(BaseModel):
    provider: str = "qwen"
    name: str = "qwen-plus"
    api_key_env: str | None = "DASHSCOPE_API_KEY"
    base_url: str | None = None


class ApprovalSettings(BaseModel):
    policy: str = "on_request"


class SandboxSettings(BaseModel):
    mode: str = "workspace_write"
    network_access: bool = False


class PathsSettings(BaseModel):
    codecraft_home: Path = Path("~/.codecraft")
    sessions_dir: Path | None = None

    @field_validator("codecraft_home", "sessions_dir")
    @classmethod
    def expand_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value.expanduser()


class RuntimeSettings(BaseModel):
    model: ModelSettings = Field(default_factory=ModelSettings)
    approval: ApprovalSettings = Field(default_factory=ApprovalSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
