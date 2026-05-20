from __future__ import annotations

import pytest
from rich.console import Console

from agent_runtime.cli.slash import SlashCommandHandler
from agent_runtime.operation.base import OperationResult
from agent_runtime.schema.decision import Decision
from agent_runtime.schema.intent import IntentPlan, IntentRequest
from agent_runtime.schema.state import AgentState
from agent_runtime.schema.step import Step
from agent_runtime.schema.strategy import Strategy


def make_handler(
        console: Console,
        state: AgentState | None = None,
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
    )


def make_state() -> AgentState:
    intent = IntentRequest(
        intent="filesystem.read",
        target={"path": "README.md"},
        params={},
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
            plan=IntentPlan(intents=[intent]),
        ),
    )
    state.recent_steps.append(
        Step(
            step_id="step-1",
            thought="read the file",
            intent=intent,
            operation="read_file",
            observation=OperationResult(
                success=True,
                content="huge observation " * 100,
            ),
            success=True,
            summary="filesystem.read -> read_file 执行成功：README.md",
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
    assert "filesystem.read" in output
    assert "huge observation" not in output
