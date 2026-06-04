from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from codecraft import (
    AgentRuntime,
    BaseTool,
    EventBus,
    LLMProvider,
    LLMProviderRegistry,
    ListFilesTool,
    ModelEvent,
    ModelEventType,
    ModelMessage,
    ModelRole,
    MockProvider,
    ReadFileTool,
    RuntimeEvent,
    RuntimeEventType,
    SessionConfig,
    SessionInput,
    SessionSource,
    SessionStore,
    ToolCall,
    ToolEffect,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    TurnContext,
    WorkspaceGuard,
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


def test_workspace_guard_rejects_path_escape(tmp_path):
    guard = WorkspaceGuard([tmp_path])

    with pytest.raises(Exception, match="outside workspace"):
        guard.resolve_read_path("../outside.txt", tmp_path)


def test_read_file_and_list_files_tools(tmp_path):
    async def run_test() -> None:
        nested = tmp_path / "pkg"
        nested.mkdir()
        target = nested / "note.txt"
        target.write_text("hello tools\n", encoding="utf-8")
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

        read_tool = ReadFileTool()
        list_tool = ListFilesTool()
        read_call = ToolCall(
            call_id="call_read",
            name="read_file",
            arguments={"path": "pkg/note.txt"},
        )
        list_call = ToolCall(
            call_id="call_list",
            name="list_files",
            arguments={"path": "pkg"},
        )

        read_result = await read_tool.arun(
            read_tool.args_schema.model_validate(read_call.arguments),
            ToolContext(context=context, call=read_call),
        )
        list_result = await list_tool.arun(
            list_tool.args_schema.model_validate(list_call.arguments),
            ToolContext(context=context, call=list_call),
        )

        assert read_result.success is True
        assert read_result.content == "hello tools\n"
        assert read_result.data["line_count"] == 1
        assert list_result.success is True
        assert list_result.content == "note.txt"

    asyncio.run(run_test())


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


def test_agent_runtime_creates_thread_and_runs_basic_turn(tmp_path):
    async def run_test() -> None:
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.MESSAGE_DELTA,
                    payload={"text": "hello "},
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_DELTA,
                    payload={"text": "runtime"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry(),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "say hello"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert [event.type for event in snapshot.events] == [
            RuntimeEventType.SESSION_STARTED,
            RuntimeEventType.TURN_STARTED,
            RuntimeEventType.USER_MESSAGE,
            RuntimeEventType.ASSISTANT_MESSAGE_DELTA,
            RuntimeEventType.ASSISTANT_MESSAGE_DELTA,
            RuntimeEventType.ASSISTANT_MESSAGE,
            RuntimeEventType.TURN_FINISHED,
        ]
        assert [event.seq for event in snapshot.events] == list(range(1, 8))
        assert snapshot.events[-1].payload["answer"] == "hello runtime"
        assert provider.calls[0][0][0].content == "say hello"

    asyncio.run(run_test())


def test_agent_thread_next_event_sees_session_started_and_turn_events(tmp_path):
    async def run_test() -> None:
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry(
                [
                    MockProvider(
                        script=[
                            ModelEvent(
                                type=ModelEventType.MESSAGE_COMPLETED,
                                payload={"text": "done"},
                            ),
                            ModelEvent(type=ModelEventType.COMPLETED),
                        ]
                    )
                ]
            ),
            tool_registry=ToolRegistry(),
        )

        thread = await runtime.create_thread(config)
        first = await thread.next_event()
        await thread.submit(SessionInput.user_message("inp_test", "finish"))
        await thread.wait_until_idle()
        second = await thread.next_event()
        third = await thread.next_event()

        assert first.type == RuntimeEventType.SESSION_STARTED
        assert second.type == RuntimeEventType.TURN_STARTED
        assert third.type == RuntimeEventType.USER_MESSAGE

    asyncio.run(run_test())


def test_runtime_resume_reconstructs_conversation_without_replaying_turn(tmp_path):
    async def run_test() -> None:
        config = make_config(tmp_path)
        store = SessionStore(config.codecraft_home)
        first_provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "first answer"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        first_runtime = AgentRuntime(
            session_store=store,
            llm_providers=LLMProviderRegistry([first_provider]),
            tool_registry=ToolRegistry(),
        )
        thread = await first_runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_one", "first"))
        await thread.wait_until_idle()

        second_provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "second answer"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        second_runtime = AgentRuntime(
            session_store=store,
            llm_providers=LLMProviderRegistry([second_provider]),
            tool_registry=ToolRegistry(),
        )
        resumed = await second_runtime.resume_thread(config.session_id)
        restored = await resumed.next_event()
        await resumed.submit(SessionInput.user_message("inp_two", "second"))
        await resumed.wait_until_idle()

        assert restored.type == RuntimeEventType.SESSION_RESTORED
        assert len(first_provider.calls) == 1
        assert len(second_provider.calls) == 1
        assert [message.content for message in second_provider.calls[0][0]] == [
            "first",
            "first answer",
            "second",
        ]

    asyncio.run(run_test())


def test_runtime_executes_read_file_tool_call_and_continues_turn(tmp_path):
    async def run_test() -> None:
        (tmp_path / "note.txt").write_text("tool loop works", encoding="utf-8")
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_read",
                        "name": "read_file",
                        "arguments": {"path": "note.txt"},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "The file says: tool loop works"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([ReadFileTool()]),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "read note"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert [event.type for event in snapshot.events] == [
            RuntimeEventType.SESSION_STARTED,
            RuntimeEventType.TURN_STARTED,
            RuntimeEventType.USER_MESSAGE,
            RuntimeEventType.MODEL_TOOL_CALL,
            RuntimeEventType.TOOL_CALL_STARTED,
            RuntimeEventType.TOOL_CALL_FINISHED,
            RuntimeEventType.ASSISTANT_MESSAGE,
            RuntimeEventType.TURN_FINISHED,
        ]
        finished = snapshot.events[5]
        assert finished.payload["result"]["success"] is True
        assert finished.payload["result"]["content"] == "tool loop works"
        assert snapshot.events[-1].payload["steps"] == 1
        assert [message.content for message in provider.calls[1][0]] == [
            "read note",
            "{'path': 'note.txt'}",
            "tool loop works",
        ]

    asyncio.run(run_test())


def test_runtime_records_failed_unknown_tool(tmp_path):
    async def run_test() -> None:
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_missing",
                        "name": "missing_tool",
                        "arguments": {},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Missing tool was reported."},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry(),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "call missing"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        finished = [
            event
            for event in snapshot.events
            if event.type == RuntimeEventType.TOOL_CALL_FINISHED
        ][0]
        assert finished.payload["result"]["success"] is False
        assert finished.payload["result"]["error"] == "tool_not_found"
        assert snapshot.events[-1].type == RuntimeEventType.TURN_FINISHED

    asyncio.run(run_test())
