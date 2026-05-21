from __future__ import annotations

from typing import Iterable

from agent_runtime.tool.provider import BuiltinToolProvider, ToolProvider
from agent_runtime.tool.registry import ToolRegistry


def create_tool_registry(
        providers: Iterable[ToolProvider] | None = None,
) -> ToolRegistry:
    """Create the default runtime tool registry."""

    return ToolRegistry(
        providers=[
            BuiltinToolProvider(),
            *(providers or []),
        ],
    )
