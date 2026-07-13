from __future__ import annotations

from pydantic import BaseModel, Field


class RenderConfig(BaseModel):
    max_tool_preview_chars: int = Field(default=800, ge=80, le=10000)
    debug: bool = False
