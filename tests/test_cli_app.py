from __future__ import annotations

import asyncio

from typer.testing import CliRunner

from codecraft.approval import ApprovalManager, ApprovalPolicy, ThreadApprovalReviewer
from codecraft.cli import app as cli_app
from codecraft.cli.app import app
from codecraft.core.runtime import AgentRuntime
from codecraft.core.ids import new_id
from codecraft.core.session_store import SessionStore
from codecraft.llm import LLMProviderRegistry, MockProvider, ModelEvent, ModelEventType
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.session import SessionConfig, SessionSource
from codecraft.tool import BashTool, ToolRegistry


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
    assert "status=valid" in result.output
    assert "events=2" in result.output


def test_sessions_all_marks_invalid_session(tmp_path):
    async def seed() -> None:
        config = make_config(tmp_path)
        bad_config = config.model_copy(update={"session_id": "ses_bad"})
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
        await store.create_session(bad_config)
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=bad_config.session_id,
                seq=2,
                type=RuntimeEventType.SESSION_STARTED,
                payload={"config": bad_config.model_dump(mode="json")},
            )
        )

    asyncio.run(seed())

    default_result = runner.invoke(
        app,
        ["sessions", "--codecraft-home", str(tmp_path / ".codecraft")],
    )
    all_result = runner.invoke(
        app,
        ["sessions", "--codecraft-home", str(tmp_path / ".codecraft"), "--all"],
    )

    assert default_result.exit_code == 0
    assert "ses_cli" in default_result.output
    assert "ses_bad" not in default_result.output
    assert all_result.exit_code == 0
    assert "ses_cli status=valid" in all_result.output
    assert "ses_bad status=invalid:session_seq_not_continuous" in all_result.output


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


def test_inspect_raw_prints_invalid_session_lines(tmp_path):
    async def seed() -> SessionConfig:
        config = make_config(tmp_path)
        store = SessionStore(config.codecraft_home)
        await store.create_session(config)
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=config.session_id,
                seq=2,
                type=RuntimeEventType.SESSION_STARTED,
                payload={"config": config.model_dump(mode="json")},
            )
        )
        return config

    config = asyncio.run(seed())

    raw_result = runner.invoke(
        app,
        [
            "inspect",
            config.session_id,
            "--codecraft-home",
            str(config.codecraft_home),
            "--raw",
        ],
    )

    assert raw_result.exit_code == 0
    assert "session_id: ses_cli" in raw_result.output
    assert "raw_lines: 1" in raw_result.output
    assert '1: {"event_id":' in raw_result.output
    assert '"seq":2' in raw_result.output


def test_inspect_command_prints_tool_and_error_summaries(tmp_path):
    async def seed() -> SessionConfig:
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
                type=RuntimeEventType.MODEL_TOOL_CALL,
                payload={
                    "call_id": "call_read",
                    "name": "read_file",
                    "arguments": {"path": "README.md"},
                },
            )
        )
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=config.session_id,
                turn_id="turn_cli",
                seq=3,
                type=RuntimeEventType.TOOL_CALL_FINISHED,
                payload={
                    "call_id": "call_read",
                    "name": "read_file",
                    "result": {
                        "success": False,
                        "content": "File does not exist.",
                        "error": "file_not_found",
                        "metadata": {},
                    },
                    "duration_ms": 4,
                },
            )
        )
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=config.session_id,
                turn_id="turn_cli",
                seq=4,
                type=RuntimeEventType.ERROR,
                payload={"message": "runtime failed"},
            )
        )
        return config

    config = asyncio.run(seed())

    result = runner.invoke(
        app,
        [
            "inspect",
            config.session_id,
            "--codecraft-home",
            str(config.codecraft_home),
            "--tools",
            "--errors",
        ],
    )

    assert result.exit_code == 0
    assert "2 model_tool_call read_file args={'path': 'README.md'}" in result.output
    assert "3 [tool] read_file failed (4ms): File does not exist." in result.output
    assert "3 tool_error read_file" in result.output
    assert "4 error turn=turn_cli" in result.output


def test_resume_last_prints_latest_session(tmp_path):
    config = seed_session(tmp_path)

    result = runner.invoke(
        app,
        ["resume", "--last", "--summary", "--codecraft-home", str(config.codecraft_home)],
    )

    assert result.exit_code == 0
    assert "session_id: ses_cli" in result.output
    assert "events: 2" in result.output


def test_resume_last_continues_latest_session(tmp_path, monkeypatch):
    async def seed() -> SessionConfig:
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
                turn_id="turn_one",
                seq=2,
                type=RuntimeEventType.USER_MESSAGE,
                payload={"text": "first"},
            )
        )
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=config.session_id,
                turn_id="turn_one",
                seq=3,
                type=RuntimeEventType.ASSISTANT_MESSAGE,
                payload={"text": "first answer"},
            )
        )
        return config

    config = asyncio.run(seed())
    provider = MockProvider(
        [
            ModelEvent(
                type=ModelEventType.MESSAGE_COMPLETED,
                payload={"text": "resumed answer"},
            ),
            ModelEvent(type=ModelEventType.COMPLETED),
        ]
    )
    monkeypatch.setattr(
        cli_app,
        "_build_provider_registry",
        lambda: LLMProviderRegistry([provider]),
    )

    result = runner.invoke(
        app,
        ["resume", "--last", "--codecraft-home", str(config.codecraft_home)],
        input="second\n/exit\n",
    )

    assert result.exit_code == 0
    assert "session_id: ses_cli" in result.output
    assert "resumed answer" in result.output
    assert [message.content for message in provider.calls[0][0][1:]] == [
        "first",
        "first answer",
        "second",
    ]


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


def test_exec_command_prints_bash_approval_details(tmp_path, monkeypatch):
    def fake_runtime(config: SessionConfig) -> AgentRuntime:
        return AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry(
                [
                    MockProvider(
                        [
                            ModelEvent(
                                type=ModelEventType.TOOL_CALL,
                                payload={
                                    "call_id": "call_bash",
                                    "name": "bash",
                                    "arguments": {"command": "python -c 'print(1)'"},
                                },
                            ),
                            ModelEvent(type=ModelEventType.COMPLETED),
                        ]
                    )
                ]
            ),
            tool_registry=ToolRegistry([BashTool()]),
            approval_manager=ApprovalManager(
                policy=ApprovalPolicy(config.approval_policy),
                reviewer=ThreadApprovalReviewer(),
            ),
        )

    monkeypatch.setattr(cli_app, "_build_runtime", fake_runtime)

    result = runner.invoke(
        app,
        [
            "exec",
            "check python",
            "--provider",
            "mock",
            "--model",
            "mock-model",
            "--approval-policy",
            "on_request",
            "--codecraft-home",
            str(tmp_path / ".codecraft"),
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "[tool] bash: python -c 'print(1)'" in result.output
    assert "[approval] bash" in result.output
    assert "command: python -c 'print(1)'" in result.output
    assert "Approve?" in result.output
    assert "[tool] bash failed" in result.output
