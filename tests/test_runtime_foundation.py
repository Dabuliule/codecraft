from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from codecraft import (
    BaseTool,
    EventBus,
    LLMProvider,
    ModelEvent,
    ModelEventType,
    ModelMessage,
    ModelRole,
    RuntimeEvent,
    RuntimeEventType,
    SessionConfig,
    SessionSource,
    SessionStore,
    ToolEffect,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    TurnContext,
    new_id,
)
from codecraft.tool import ToolContext


def make_config(tmp_path) -> SessionConfig:
    return SessionConfig(
        session_id="ses_test",
        thread_id="thr_test",
        source=SessionSource.TEST,
        cwd=tmp_path,
        workspace_roots=[tmp_path],
        codecraft_home=tmp_path / ".codecraft",
        model="mock-model",
        model_provider="mock",
        approval_policy="never",
        sandbox_mode="workspace_write",
    )


def test_runtime_event_is_json_serializable(tmp_path):
    config = make_config(tmp_path)
    event = RuntimeEvent(
        event_id="evt_test",
        session_id=config.session_id,
        seq=1,
        type=RuntimeEventType.SESSION_STARTED,
        payload={"config": config.model_dump(mode="json")},
    )

    encoded = event.model_dump_json()
    decoded = RuntimeEvent.model_validate_json(encoded)

    assert decoded.type == RuntimeEventType.SESSION_STARTED
    assert decoded.seq == 1
    assert decoded.payload["config"]["session_id"] == "ses_test"


def test_runtime_event_requires_positive_seq():
    with pytest.raises(ValueError):
        RuntimeEvent(
            event_id="evt_bad",
            session_id="ses_test",
            seq=0,
            type=RuntimeEventType.SESSION_STARTED,
        )


def test_event_bus_dispatches_runtime_events_in_subscription_order():
    async def run_test() -> None:
        calls: list[tuple[str, int]] = []
        bus = EventBus()

        async def first(event: RuntimeEvent) -> None:
            calls.append(("first", event.seq))

        async def second(event: RuntimeEvent) -> None:
            calls.append(("second", event.seq))

        bus.subscribe(first)
        bus.subscribe(second)
        await bus.emit(
            RuntimeEvent(
                event_id="evt_test",
                session_id="ses_test",
                seq=1,
                type=RuntimeEventType.SESSION_STARTED,
            )
        )

        assert calls == [("first", 1), ("second", 1)]

    asyncio.run(run_test())


def test_tool_result_enforces_error_shape():
    assert ToolResult(success=True, content="ok").error is None

    with pytest.raises(ValueError):
        ToolResult(success=True, content="ok", error="unexpected")

    with pytest.raises(ValueError):
        ToolResult(success=False, content="failed")


def test_tool_registry_registers_and_lists_specs():
    class EchoArgs(BaseModel):
        text: str

    class EchoTool(BaseTool):
        name = "echo"
        description = "Echo text."
        args_schema = EchoArgs
        effects = {ToolEffect.READ_ONLY}

        async def arun(self, args: EchoArgs, context: ToolContext) -> ToolResult:
            return ToolResult(success=True, content=args.text)

    registry = ToolRegistry([EchoTool()])

    assert registry.get("echo").name == "echo"
    assert registry.specs() == [
        ToolSpec(
            name="echo",
            description="Echo text.",
            input_schema=EchoArgs.model_json_schema(),
            effects={ToolEffect.READ_ONLY},
        )
    ]


def test_session_config_normalizes_paths(tmp_path):
    config = make_config(tmp_path)

    assert config.cwd == tmp_path.resolve()
    assert config.workspace_roots == [tmp_path.resolve()]
    assert config.codecraft_home == (tmp_path / ".codecraft").resolve()


def test_turn_context_is_immutable(tmp_path):
    config = make_config(tmp_path)
    context = TurnContext(
        session_id=config.session_id,
        thread_id=config.thread_id,
        turn_id="turn_test",
        cwd=config.cwd,
        workspace_roots=config.workspace_roots,
        model=config.model,
        model_provider=config.model_provider,
        approval_policy=config.approval_policy,
        sandbox_mode=config.sandbox_mode,
        network_access=config.network_access,
        available_tools=[
            ToolSpec(
                name="read_file",
                description="Read a workspace file.",
                input_schema={"type": "object"},
                effects={ToolEffect.READ_ONLY},
            )
        ],
        max_steps=config.max_turn_steps,
        max_tool_output_chars=config.max_tool_output_chars,
        created_at=config.created_at,
    )

    with pytest.raises(ValueError):
        context.turn_id = "turn_other"


def test_llm_provider_stream_contract(tmp_path):
    class MockProvider(LLMProvider):
        name = "mock"

        async def stream(
            self,
            messages: list[ModelMessage],
            tools: list[ToolSpec],
            context: TurnContext,
        ) -> AsyncIterator[ModelEvent]:
            yield ModelEvent(
                type=ModelEventType.MESSAGE_COMPLETED,
                payload={"text": messages[0].content},
            )
            yield ModelEvent(type=ModelEventType.COMPLETED)

    config = make_config(tmp_path)
    context = TurnContext(
        session_id=config.session_id,
        thread_id=config.thread_id,
        turn_id="turn_test",
        cwd=config.cwd,
        workspace_roots=config.workspace_roots,
        model=config.model,
        model_provider=config.model_provider,
        approval_policy=config.approval_policy,
        sandbox_mode=config.sandbox_mode,
        network_access=config.network_access,
        available_tools=[],
        max_steps=config.max_turn_steps,
        max_tool_output_chars=config.max_tool_output_chars,
        created_at=config.created_at,
    )

    async def collect() -> list[ModelEvent]:
        provider = MockProvider()
        return [
            event
            async for event in provider.stream(
                [ModelMessage(role=ModelRole.USER, content="hello")],
                [],
                context,
            )
        ]

    events = asyncio.run(collect())

    assert [event.type for event in events] == [
        ModelEventType.MESSAGE_COMPLETED,
        ModelEventType.COMPLETED,
    ]
    assert events[0].payload["text"] == "hello"


def test_session_store_appends_loads_lists_and_resumes(tmp_path):
    async def run_test() -> None:
        config = make_config(tmp_path)
        store = SessionStore(config.codecraft_home)
        path = await store.create_session(config)

        assert path.exists()

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
                turn_id="turn_test",
                seq=2,
                type=RuntimeEventType.TURN_STARTED,
                payload={"input_id": "inp_test"},
            )
        )

        events = await store.load_events(config.session_id)
        summaries = await store.list_sessions(cwd=tmp_path)
        snapshot = await store.resume_last(cwd=tmp_path)

        assert [event.seq for event in events] == [1, 2]
        assert summaries[0].session_id == config.session_id
        assert summaries[0].event_count == 2
        assert snapshot.config.session_id == config.session_id
        assert [event.type for event in snapshot.events] == [
            RuntimeEventType.SESSION_STARTED,
            RuntimeEventType.TURN_STARTED,
        ]

    asyncio.run(run_test())


def test_session_store_rejects_seq_gaps(tmp_path):
    async def run_test() -> None:
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

        with pytest.raises(Exception, match="sequence"):
            await store.load_events(config.session_id)

    asyncio.run(run_test())
