from __future__ import annotations

import pytest
from rich.console import Console

from agent_runtime.cli.slash import SlashCommandHandler
from agent_runtime.core.trace import JsonlTraceWriter
from agent_runtime.schema.decision import Decision
from agent_runtime.schema.event import ThoughtEvent
from agent_runtime.schema.state import AgentState
from agent_runtime.schema.step import Step
from agent_runtime.schema.strategy import Strategy
from agent_runtime.schema.tool import ToolCall, ToolPlan
from agent_runtime.tool.base import ToolResult


def make_handler(
        console: Console,
        state: AgentState | None = None,
        trace_writer: JsonlTraceWriter | None = None,
) -> SlashCommandHandler:
    verbose = False

    def set_verbose(value: bool) -> None:
        nonlocal verbose
        verbose = value

    return SlashCommandHandler(
        console=console,
        get_state=lambda: state,
        get_verbose=lambda: verbose,
        set_verbose=set_verbose,
        render_welcome=lambda: None,
        trace_writer=trace_writer,
    )


def make_state() -> AgentState:
    tool_call = ToolCall(
        tool="read_file",
        args={"path": "README.md"},
        purpose="inspect readme",
    )
    state = AgentState(
        trace_id="trace-1",
        task="inspect",
        strategy=Strategy(
            objective="inspect",
            current_focus="read",
            approach="step",
        ),
        current_decision=Decision(
            thought="read the file",
            plan=ToolPlan(tools=[tool_call]),
        ),
    )
    state.recent_steps.append(
        Step(
            step_id="step-1",
            thought="read the file",
            tool_call=tool_call,
            observation=ToolResult(
                success=True,
                content="huge observation " * 100,
            ),
            success=True,
            summary="read_file 执行成功：README.md",
        )
    )
    return state


@pytest.mark.anyio
async def test_slash_exit_returns_exit_result():
    console = Console(record=True)
    handler = make_handler(console)

    result = await handler.handle("/exit")

    assert result.should_exit is True


@pytest.mark.anyio
async def test_slash_unknown_command_is_friendly():
    console = Console(record=True, width=100)
    handler = make_handler(console)

    await handler.handle("/missing")

    output = console.export_text()
    assert "Unknown command: /missing" in output
    assert "/help" in output


@pytest.mark.anyio
async def test_slash_status_shows_runtime_state():
    console = Console(record=True, width=120)
    handler = make_handler(console, make_state())

    await handler.handle("/status")

    output = console.export_text()
    assert "trace-1" in output
    assert "history_steps" in output
    assert "1" in output


@pytest.mark.anyio
async def test_slash_history_does_not_print_huge_observation():
    console = Console(record=True, width=120)
    handler = make_handler(console, make_state())

    await handler.handle("/history")

    output = console.export_text()
    assert "step-1" in output
    assert "read_file" in output
    assert "huge observation" not in output


@pytest.mark.anyio
async def test_slash_trace_shows_current_trace_summary(tmp_path):
    console = Console(record=True, width=120)
    state = make_state()
    trace_writer = JsonlTraceWriter(trace_dir=tmp_path)
    await trace_writer.handle(
        ThoughtEvent(
            trace_id=state.trace_id,
            thought="inspect",
        )
    )

    handler = make_handler(console, state, trace_writer)

    await handler.handle("/trace")

    output = console.export_text()

    assert "trace_id: trace-1" in output
    assert "events: 1" in output
    assert "thought=1" in output
