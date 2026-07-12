from __future__ import annotations

import asyncio

from typer.testing import CliRunner

from codecraft.approval import (
    ApprovalManager,
    ApprovalPolicy,
    ThreadApprovalReviewer,
)
from codecraft.cli.app import app
from codecraft.core.runtime import AgentRuntime
from codecraft.core.session_store import SessionStore
from codecraft.llm import (
    LLMProviderRegistry,
    MockProvider,
    ModelEvent,
    ModelEventType,
)
from codecraft.schema.session import SessionConfig, SessionSource
from codecraft.tool import ToolRegistry, WriteFileTool
from codecraft.tui import ApprovalScreen, CodeCraftTUI, MessageBlock

runner = CliRunner()


def _config(tmp_path, *, approval_policy=ApprovalPolicy.NEVER) -> SessionConfig:
    return SessionConfig(
        session_id="ses_tui",
        thread_id="thr_tui",
        source=SessionSource.CLI_TUI,
        cwd=tmp_path,
        workspace_roots=[tmp_path],
        codecraft_home=tmp_path / ".codecraft",
        model="mock-model",
        model_provider="mock",
        approval_policy=approval_policy,
        sandbox_mode="workspace_write",
    )


async def _wait_until(pilot, predicate, *, attempts=100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await pilot.pause(0.01)
    raise AssertionError("TUI condition was not reached")


def test_tui_streams_messages_and_updates_runtime_status(tmp_path):
    async def run_test():
        config = _config(tmp_path)
        provider = MockProvider(
            [
                ModelEvent(
                    type=ModelEventType.MESSAGE_DELTA,
                    payload={"text": "Hello "},
                ),
                ModelEvent(
                    type=ModelEventType.TOKEN_COUNT,
                    payload={
                        "input_tokens": 3,
                        "output_tokens": 2,
                        "total_tokens": 5,
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_DELTA,
                    payload={"text": "world"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry(),
        )
        tui = CodeCraftTUI(config, runtime)

        async with tui.run_test(size=(80, 24)) as pilot:
            await _wait_until(pilot, lambda: tui.turn_status == "idle")
            prompt = tui.query_one("#prompt")
            prompt.value = "hello request"
            await pilot.press("enter")
            await _wait_until(
                pilot,
                lambda: (
                    tui.turn_status == "idle"
                    and len(list(tui.query(MessageBlock))) == 2
                ),
            )

            messages = list(tui.query(MessageBlock))
            assert [(message.role, message.text) for message in messages] == [
                ("User", "hello request"),
                ("Assistant", "Hello world"),
            ]
            assert tui.token_usage == {
                "input_tokens": 3,
                "output_tokens": 2,
                "total_tokens": 5,
            }
            assert prompt.disabled is False
            conversation = tui.query_one("#conversation-pane")
            side_panel = tui.query_one("#side-panel")
            main = tui.query_one("#main")
            assert conversation.region.right <= side_panel.region.x
            assert main.region.bottom <= prompt.region.y
            assert conversation.region.width >= 30

    asyncio.run(run_test())


def test_tui_approval_modal_controls_side_effect(tmp_path):
    async def run_test():
        config = _config(tmp_path, approval_policy=ApprovalPolicy.ON_REQUEST)
        provider = MockProvider(
            [
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_write",
                        "name": "write_file",
                        "arguments": {
                            "path": "approved.txt",
                            "content": "approved by TUI\n",
                        },
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "File created."},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([WriteFileTool()]),
            approval_manager=ApprovalManager(
                policy=ApprovalPolicy.ON_REQUEST,
                reviewer=ThreadApprovalReviewer(),
            ),
        )
        tui = CodeCraftTUI(config, runtime)

        async with tui.run_test(size=(120, 40)) as pilot:
            await _wait_until(pilot, lambda: tui.turn_status == "idle")
            prompt = tui.query_one("#prompt")
            prompt.value = "create a file"
            await pilot.press("enter")
            await _wait_until(pilot, lambda: isinstance(tui.screen, ApprovalScreen))

            assert not (tmp_path / "approved.txt").exists()
            assert tui.screen.focused is not None
            assert tui.screen.focused.id == "reject"
            clicked = await pilot.click("#approve")
            assert clicked is True

            await _wait_until(
                pilot,
                lambda: (
                    tui.turn_status == "idle" and (tmp_path / "approved.txt").exists()
                ),
            )
            assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == (
                "approved by TUI\n"
            )
            assert list(tui.query(MessageBlock))[-1].text == "File created."

    asyncio.run(run_test())


def test_tui_command_uses_tui_session_source(tmp_path, monkeypatch):
    captured: list[SessionConfig] = []

    def fake_run(self) -> None:
        captured.append(self.config)

    monkeypatch.setattr(CodeCraftTUI, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "tui",
            "--provider",
            "mock",
            "--model",
            "mock-model",
            "--codecraft-home",
            str(tmp_path / ".codecraft"),
        ],
    )

    assert result.exit_code == 0
    assert captured[0].source == SessionSource.CLI_TUI
    assert captured[0].model_provider == "mock"
