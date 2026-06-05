from __future__ import annotations

import asyncio

from typer.testing import CliRunner

from codecraft.cli import app as cli_app
from codecraft.cli.app import app
from codecraft.core.runtime import AgentRuntime
from codecraft.core.ids import new_id
from codecraft.core.session_store import SessionStore
from codecraft.llm import LLMProviderRegistry, MockProvider, ModelEvent, ModelEventType
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.session import SessionConfig, SessionSource
from codecraft.tool import ToolRegistry


runner = CliRunner()


def make_config(tmp_path) -> SessionConfig:
    return SessionConfig(
        session_id="ses_cli",
        thread_id="thr_cli",
        source=SessionSource.TEST,
        cwd=tmp_path,
        workspace_roots=[tmp_path],
        codecraft_home=tmp_path / ".codecraft",
        model="mock-model",
        model_provider="mock",
        approval_policy="never",
        sandbox_mode="workspace_write",
    )


def seed_session(tmp_path) -> SessionConfig:
    async def run() -> SessionConfig:
        config = make_config(tmp_path)
        store = SessionStore(config.codecraft_home)
        await store.create_session(config)
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=config.session_id,
                seq=1,
                type=RuntimeEventType.SESSION_STARTED,
                payload={"config": config.model_dump(mode="json")},
            )
        )
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=config.session_id,
                turn_id="turn_cli",
                seq=2,
                type=RuntimeEventType.TURN_FINISHED,
                payload={"answer": "done", "status": "success"},
            )
        )
        return config

    return asyncio.run(run())


def test_sessions_command_lists_session(tmp_path):
    config = seed_session(tmp_path)

    result = runner.invoke(
        app,
        ["sessions", "--codecraft-home", str(config.codecraft_home)],
    )

    assert result.exit_code == 0
    assert "ses_cli" in result.output
    assert "events=2" in result.output


def test_inspect_command_prints_summary_and_events(tmp_path):
    config = seed_session(tmp_path)

    result = runner.invoke(
        app,
        [
            "inspect",
            config.session_id,
            "--codecraft-home",
            str(config.codecraft_home),
            "--events",
        ],
    )

    assert result.exit_code == 0
    assert "session_id: ses_cli" in result.output
    assert "events: 2" in result.output
    assert "final_answer: done" in result.output
    assert "2 turn_finished" in result.output


def test_resume_last_prints_latest_session(tmp_path):
    config = seed_session(tmp_path)

    result = runner.invoke(
        app,
        ["resume", "--last", "--codecraft-home", str(config.codecraft_home)],
    )

    assert result.exit_code == 0
    assert "session_id: ses_cli" in result.output
    assert "events: 2" in result.output


def test_exec_command_runs_runtime_and_prints_answer(tmp_path, monkeypatch):
    seen_configs: list[SessionConfig] = []

    def fake_runtime(config: SessionConfig) -> AgentRuntime:
        seen_configs.append(config)
        return AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry(
                [
                    MockProvider(
                        [
                            ModelEvent(
                                type=ModelEventType.MESSAGE_COMPLETED,
                                payload={"text": "exec answer"},
                            ),
                            ModelEvent(type=ModelEventType.COMPLETED),
                        ]
                    )
                ]
            ),
            tool_registry=ToolRegistry(),
        )

    monkeypatch.setattr(cli_app, "_build_runtime", fake_runtime)

    result = runner.invoke(
        app,
        [
            "exec",
            "answer",
            "--provider",
            "mock",
            "--model",
            "mock-model",
            "--codecraft-home",
            str(tmp_path / ".codecraft"),
        ],
    )

    assert result.exit_code == 0
    assert "exec answer" in result.output
    assert seen_configs[0].model_provider == "mock"
    assert seen_configs[0].model == "mock-model"

    sessions_result = runner.invoke(
        app,
        ["sessions", "--codecraft-home", str(tmp_path / ".codecraft")],
    )
    assert sessions_result.exit_code == 0
    assert "events=5" in sessions_result.output


def test_exec_command_loads_config_file_defaults(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[model]
provider = "mock"
name = "configured-model"

[instructions]
user = "Be terse."
""",
        encoding="utf-8",
    )
    seen_configs: list[SessionConfig] = []

    def fake_runtime(config: SessionConfig) -> AgentRuntime:
        seen_configs.append(config)
        return AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry(
                [
                    MockProvider(
                        [
                            ModelEvent(
                                type=ModelEventType.MESSAGE_COMPLETED,
                                payload={"text": "configured answer"},
                            ),
                            ModelEvent(type=ModelEventType.COMPLETED),
                        ]
                    )
                ]
            ),
            tool_registry=ToolRegistry(),
        )

    monkeypatch.setattr(cli_app, "_build_runtime", fake_runtime)

    result = runner.invoke(
        app,
        [
            "exec",
            "answer",
            "--config",
            str(config_path),
            "--codecraft-home",
            str(tmp_path / ".codecraft"),
        ],
    )

    assert result.exit_code == 0
    assert "configured answer" in result.output
    assert seen_configs[0].model_provider == "mock"
    assert seen_configs[0].model == "configured-model"
    assert seen_configs[0].user_instructions == "Be terse."


def test_chat_command_runs_multiple_turns_until_exit(tmp_path, monkeypatch):
    seen_configs: list[SessionConfig] = []

    def fake_runtime(config: SessionConfig) -> AgentRuntime:
        seen_configs.append(config)
        return AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry(
                [
                    MockProvider(
                        [
                            ModelEvent(
                                type=ModelEventType.MESSAGE_COMPLETED,
                                payload={"text": "first answer"},
                            ),
                            ModelEvent(type=ModelEventType.COMPLETED),
                            ModelEvent(
                                type=ModelEventType.MESSAGE_COMPLETED,
                                payload={"text": "second answer"},
                            ),
                            ModelEvent(type=ModelEventType.COMPLETED),
                        ]
                    )
                ]
            ),
            tool_registry=ToolRegistry(),
        )

    monkeypatch.setattr(cli_app, "_build_runtime", fake_runtime)

    result = runner.invoke(
        app,
        [
            "chat",
            "--provider",
            "mock",
            "--model",
            "mock-model",
            "--codecraft-home",
            str(tmp_path / ".codecraft"),
        ],
        input="first\nsecond\n/exit\n",
    )

    assert result.exit_code == 0
    assert "session_id:" in result.output
    assert "first answer" in result.output
    assert "second answer" in result.output
    assert seen_configs[0].source == SessionSource.CLI_CHAT
    assert seen_configs[0].model_provider == "mock"
