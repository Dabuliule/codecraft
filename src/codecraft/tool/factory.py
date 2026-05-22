from __future__ import annotations

from os import PathLike
from typing import Iterable

from codecraft.tool.provider import BuiltinToolProvider, ToolProvider
from codecraft.tool.registry import ToolRegistry


def create_tool_registry(
        providers: Iterable[ToolProvider] | None = None,
        workspace_root: str | PathLike[str] | None = None,
) -> ToolRegistry:
    """Create the default runtime tool registry."""

    return ToolRegistry(
        providers=[
            BuiltinToolProvider(workspace_root=workspace_root),
            *(providers or []),
        ],
    )
