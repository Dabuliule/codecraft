from __future__ import annotations

import json
from typing import Any

import pytest

from agent_runtime.core.agent import Agent
from agent_runtime.core.event_bus import EventBus
from agent_runtime.core.executor import Executor
from agent_runtime.core.runtime import AgentRuntime
from agent_runtime.llm.base import BaseLLM, LLMResponse
from agent_runtime.schema.event import ObservationEvent
from agent_runtime.tool.factory import create_tool_registry


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


@pytest.mark.anyio
async def test_runtime_runs_read_file_then_final_answer(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("hello runtime", encoding="utf-8")

    llm = ScriptedLLM(
        responses=[
            {
                "thought": "Read the file before answering.",
                "plan": {
                    "tools": [
                        {
                            "tool": "read_file",
                            "args": {"path": "note.txt"},
                            "purpose": "Inspect the file content.",
                        }
                    ]
                },
            },
            {
                "thought": "The file content is known; produce the answer.",
                "plan": {
                    "tools": [
                        {
                            "tool": "final_answer",
                            "args": {"answer": "The file says: hello runtime"},
                            "purpose": "Finish the task.",
                        }
                    ]
                },
                "is_terminal": True,
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
                "thought": "Try a shell command.",
                "plan": {
                    "tools": [
                        {
                            "tool": "shell_exec",
                            "args": {"command": "python -V"},
                            "purpose": "Inspect Python version.",
                        }
                    ]
                },
            },
            {
                "thought": "Report that approval is required.",
                "plan": {
                    "tools": [
                        {
                            "tool": "final_answer",
                            "args": {"answer": "Approval is required."},
                            "purpose": "Finish.",
                        }
                    ]
                },
                "is_terminal": True,
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
