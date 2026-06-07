from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RenderConfig(BaseModel):
    mode: Literal["rich-shell", "fullscreen"] = "rich-shell"
    theme: Literal["auto", "dark", "light"] = "auto"
    show_tool_args: Literal["hidden", "compact", "full"] = "compact"
    show_model_tool_call: bool = False
    show_token_usage: bool = True
    show_elapsed_time: bool = True
    max_tool_preview_chars: int = Field(default=800, ge=80, le=10000)
    ascii: bool = False
    debug: bool = False
