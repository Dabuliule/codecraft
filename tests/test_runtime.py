from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import pytest

from codecraft.core.agent import Agent
from codecraft.core.event_bus import EventBus
from codecraft.core.executor import Executor
from codecraft.core.runtime import AgentRuntime
from codecraft.llm.base import BaseLLM, LLMResponse
from codecraft.schema.event import ObservationEvent, ToolExecutionEvent
from codecraft.tool.base import BaseTool
from codecraft.tool.factory import create_tool_registry
from codecraft.tool.provider import ToolProvider


class ScriptedLLM(BaseLLM):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.messages: list[list[dict[str, Any]]] = []

    async def agenerate(
            self,
            messages: list[dict[str, Any]],
            **kwargs: Any,
    ) -> LLMResponse:
        self.messages.append(messages)

        if not self._responses:
            raise AssertionError("ScriptedLLM received more calls than expected")

        return LLMResponse(
            content=json.dumps(self._responses.pop(0), ensure_ascii=False),
            finish_reason="stop",
        )


class RecordingTool(BaseTool):
    name = "record_marker"
    description = "Record when the tool actually executes."

    def __init__(self, markers: list[str]) -> None:
        self.markers = markers

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        self.markers.append("tool_executed")
        return {"content": "recorded"}


class RecordingProvider(ToolProvider):
    name = "recording"

    def __init__(self, markers: list[str]) -> None:
        self.markers = markers

    def tools(self) -> Iterable[BaseTool]:
        return (RecordingTool(self.markers),)


@pytest.mark.anyio
async def test_runtime_runs_read_file_then_final_answer(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("hello runtime", encoding="utf-8")

    llm = ScriptedLLM(
        responses=[
            {
                "rationale": "Read the file before answering.",
                "tool_call": {
                    "tool": "read_file",
                    "args": {"path": "note.txt"},
                    "purpose": "Inspect the file content.",
                },
            },
            {
                "rationale": "The file content is known; produce the answer.",
                "tool_call": {
                    "tool": "final_answer",
                    "args": {"answer": "The file says: hello runtime"},
                    "purpose": "Finish the task.",
                },
            },
        ]
    )

    events = []

    async def collect(event):
        events.append(event)

    event_bus = EventBus()
    event_bus.subscribe(collect)

    registry = create_tool_registry(workspace_root=tmp_path)
    runtime = AgentRuntime(
        agent=Agent(llm=llm, tool_registry=registry),
        executor=Executor(tool_registry=registry),
        event_bus=event_bus,
    )

    result = await runtime.arun("Read note.txt and answer with its content.")

    assert result.success is True
    assert result.answer == "The file says: hello runtime"
    assert result.total_steps == 2
    assert [step.tool_call.tool for step in result.steps] == [
        "read_file",
        "final_answer",
    ]
    assert result.steps[0].observation.content == "hello runtime"
    assert len(llm.messages) == 2

    assert [event.type for event in events] == [
        "thought",
        "tool_call",
        "tool_execution",
        "observation",
        "thought",
        "tool_call",
        "tool_execution",
        "observation",
        "final_result",
    ]


@pytest.mark.anyio
async def test_runtime_includes_policy_data_in_observation_events(tmp_path):
    llm = ScriptedLLM(
        responses=[
            {
                "rationale": "Try a shell command.",
                "tool_call": {
                    "tool": "shell_exec",
                    "args": {"command": "python -V"},
                    "purpose": "Inspect Python version.",
                },
            },
            {
                "rationale": "Report that approval is required.",
                "tool_call": {
                    "tool": "final_answer",
                    "args": {"answer": "Approval is required."},
                    "purpose": "Finish.",
                },
            },
        ]
    )

    events = []

    async def collect(event):
        events.append(event)

    event_bus = EventBus()
    event_bus.subscribe(collect)

    registry = create_tool_registry(workspace_root=tmp_path)
    runtime = AgentRuntime(
        agent=Agent(llm=llm, tool_registry=registry),
        executor=Executor(tool_registry=registry),
        event_bus=event_bus,
    )

    await runtime.arun("Check Python version.")

    observations = [
        event for event in events
        if isinstance(event, ObservationEvent)
    ]

    assert observations[0].data["policy"]["action"] == "require_approval"
    assert observations[0].data["policy"]["data"]["tool"] == "shell_exec"


@pytest.mark.anyio
async def test_runtime_emits_tool_execution_before_tool_runs(tmp_path):
    markers: list[str] = []
    llm = ScriptedLLM(
        responses=[
            {
                "rationale": "Record execution timing.",
                "tool_call": {
                    "tool": "record_marker",
                    "args": {},
                    "purpose": "Check event ordering.",
                },
            },
            {
                "rationale": "Finish after recording.",
                "tool_call": {
                    "tool": "final_answer",
                    "args": {"answer": "done"},
                    "purpose": "Finish.",
                },
            },
        ]
    )

    async def collect(event):
        if (
                isinstance(event, ToolExecutionEvent)
                and event.tool == "record_marker"
        ):
            markers.append("tool_execution_event")

    event_bus = EventBus()
    event_bus.subscribe(collect)

    registry = create_tool_registry(
        providers=[RecordingProvider(markers)],
        workspace_root=tmp_path,
    )
    runtime = AgentRuntime(
        agent=Agent(llm=llm, tool_registry=registry),
        executor=Executor(tool_registry=registry),
        event_bus=event_bus,
    )

    await runtime.arun("Record timing.")

    assert markers == [
        "tool_execution_event",
        "tool_executed",
    ]
