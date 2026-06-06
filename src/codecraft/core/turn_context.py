from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from codecraft.schema.tool import ToolSpec


class TurnContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    thread_id: str
    turn_id: str

    cwd: Path
    workspace_roots: list[Path]

    model: str
    model_provider: str

    approval_policy: str
    sandbox_mode: str
    network_access: bool

    available_tools: list[ToolSpec]

    max_steps: int
    max_tool_output_chars: int

    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
