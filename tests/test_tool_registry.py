from __future__ import annotations

import pytest
from typing import Iterable

from agent_runtime.tool.base import BaseTool
from agent_runtime.tool.factory import create_tool_registry
from agent_runtime.tool.provider import ToolProvider
from agent_runtime.tool.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo input."

    def execute(self, **kwargs):
        return {"content": kwargs.get("text", "")}


class EchoToolProvider(ToolProvider):
    name = "echo_provider"

    def tools(self) -> Iterable[BaseTool]:
        return (EchoTool(),)


def test_tool_registry_registers_tools_from_provider():
    registry = ToolRegistry(
        providers=[EchoToolProvider()],
    )

    assert registry.names() == ["echo"]
    assert registry.require("echo").name == "echo"


def test_create_tool_registry_registers_builtin_provider():
    registry = create_tool_registry()

    assert "read_file" in registry
    assert "final_answer" in registry


def test_create_tool_registry_accepts_extra_providers():
    registry = create_tool_registry(
        providers=[EchoToolProvider()],
    )

    assert "read_file" in registry
    assert "echo" in registry


def test_tool_registry_rejects_duplicate_tool_names():
    with pytest.raises(ValueError, match="Tool 'echo' 已被注册"):
        ToolRegistry(
            providers=[
                EchoToolProvider(),
                EchoToolProvider(),
            ],
        )
