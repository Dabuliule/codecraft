from __future__ import annotations

import asyncio

from typer.testing import CliRunner

from codecraft.cli.app import app
from codecraft.core.ids import new_id
from codecraft.core.session_store import SessionStore
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.session import SessionConfig, SessionSource


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
