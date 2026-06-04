from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from codecraft.schema.event import RuntimeEvent


class SessionSource(StrEnum):
    CLI_CHAT = "cli_chat"
    CLI_EXEC = "cli_exec"
    RESUME = "resume"
    TEST = "test"


class SessionConfig(BaseModel):
    session_id: str
    thread_id: str
    source: SessionSource

    cwd: Path
    workspace_roots: list[Path]
    codecraft_home: Path

    model: str
    model_provider: str

    approval_policy: str
    sandbox_mode: str
    network_access: bool = False

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

        if not self.approval_policy:
            raise ValueError("approval_policy must not be empty")

        if not self.sandbox_mode:
            raise ValueError("sandbox_mode must not be empty")

        return self


class SessionSummary(BaseModel):
    session_id: str
    thread_id: str
    path: Path
    cwd: Path | None = None
    source: SessionSource | None = None
    created_at: datetime | None = None
    last_event_at: datetime | None = None
    event_count: int = 0


class SessionSnapshot(BaseModel):
    config: SessionConfig
    events: list[RuntimeEvent]
