from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from codecraft.approval.policy import ApprovalPolicy
from codecraft.sandbox.policy import SandboxMode
from codecraft.schema.tool import ToolSpec


class TurnContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    turn_id: str

    cwd: Path
    workspace_roots: list[Path]

    model: str
    model_provider: str

    approval_policy: ApprovalPolicy
    sandbox_mode: SandboxMode
    network_access: bool
    sandbox_env_allowlist: list[str] = Field(default_factory=list)

    available_tools: list[ToolSpec]

    max_tool_calls: int
    max_tool_output_chars: int
    turn_timeout_seconds: int = 1800
    tool_timeout_seconds: int = 300
    approval_timeout_seconds: int = 300
    max_context_chars: int = 400_000
    context_keep_recent_items: int = 12
    max_parallel_read_tools: int = 4

    created_at: datetime
