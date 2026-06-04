from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class SandboxMode(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class SandboxPolicy(BaseModel):
    mode: SandboxMode
    workspace_roots: list[Path]
    network_access: bool = False
    writable_roots: list[Path] = Field(default_factory=list)
