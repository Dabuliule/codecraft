from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from codecraft.tool.base import BaseTool, ToolException


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(...)


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo text."
    input_schema = EchoArgs

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return {"content": kwargs["text"], "data": kwargs}


class FailingTool(BaseTool):
    name = "fail"
    description = "Fail with a controlled tool exception."

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        raise ToolException("planned failure", suggestion="use another input")


class SlowTool(BaseTool):
    name = "slow"
    description = "Sleep longer than the configured timeout."
    timeout = 0.01

    async def aexecute(self, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(1)
        return {"content": "finished"}


class FlakyTool(BaseTool):
    name = "flaky"
    description = "Fail once and then succeed."
    max_retries = 1
    retry_delay = 0

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return {"content": "recovered", "data": {"calls": self.calls}}


class NonIdempotentFlakyTool(FlakyTool):
    name = "non_idempotent_flaky"
    idempotent = False


@pytest.mark.anyio
async def test_base_tool_validates_input_and_returns_tool_result():
    result = await EchoTool().arun({"text": "hello"})

    assert result.success is True
    assert result.content == "hello"
    assert result.data == {"text": "hello"}


@pytest.mark.anyio
async def test_base_tool_rejects_invalid_input():
    result = await EchoTool().arun({"text": "hello", "extra": "nope"})

    assert result.success is False
    assert result.content == ""
    assert result.error is not None
    assert result.error.startswith("参数校验失败:")
    assert result.suggestion == "请根据工具输入结构修正参数后重试。"


@pytest.mark.anyio
async def test_base_tool_normalizes_tool_exception():
    result = await FailingTool().arun()

    assert result.success is False
    assert result.error == "planned failure"
    assert result.suggestion == "use another input"


@pytest.mark.anyio
async def test_base_tool_returns_timeout_failure():
    result = await SlowTool().arun()

    assert result.success is False
    assert result.error == "执行失败: Tool 执行超时 (0.01s)"
    assert result.suggestion == "请稍后重试或检查 Tool 状态。"


@pytest.mark.anyio
async def test_base_tool_retries_idempotent_failures():
    tool = FlakyTool()

    result = await tool.arun()

    assert result.success is True
    assert result.content == "recovered"
    assert result.data == {"calls": 2}
    assert tool.calls == 2


@pytest.mark.anyio
async def test_base_tool_does_not_retry_non_idempotent_failures():
    tool = NonIdempotentFlakyTool()

    result = await tool.arun()

    assert result.success is False
    assert result.error == "执行失败: temporary failure"
    assert tool.calls == 1
