from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from codecraft import (
    AgentRuntime,
    ApprovalManager,
    ApprovalPolicy,
    ApplyPatchTool,
    AutoApprovalReviewer,
    BashTool,
    BaseTool,
    EventBus,
    LLMProvider,
    LLMProviderRegistry,
    ListFilesTool,
    ModelEvent,
    ModelEventType,
    ModelMessage,
    ModelMessageType,
    ModelRole,
    MockProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    QwenProvider,
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
    ThreadApprovalReviewer,
    TurnContext,
    WorkspaceGuard,
    WriteFileTool,
    new_id,
)
from codecraft.sandbox import CommandPolicy, CommandRisk
from codecraft.prompt import InstructionLoader
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


async def next_event_of_type(thread, event_type: RuntimeEventType) -> RuntimeEvent:
    while True:
        event = await thread.next_event()
        if event.type == event_type:
            return event


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


def test_session_emit_rolls_back_seq_when_append_fails(tmp_path):
    class FailingStore(SessionStore):
        def __init__(self, codecraft_home):
            super().__init__(codecraft_home)
            self.calls = 0

        async def append_event(self, event: RuntimeEvent) -> None:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("append failed")
            await super().append_event(event)

    async def run_test() -> None:
        config = make_config(tmp_path)
        store = FailingStore(config.codecraft_home)
        runtime = AgentRuntime(
            session_store=store,
            llm_providers=LLMProviderRegistry([MockProvider()]),
            tool_registry=ToolRegistry(),
        )
        thread = await runtime.create_thread(config)

        with pytest.raises(RuntimeError, match="append failed"):
            await thread.session.emit(RuntimeEventType.USER_MESSAGE, {"text": "failed"})

        event = await thread.session.emit(RuntimeEventType.USER_MESSAGE, {"text": "ok"})
        loaded = await store.load_events(config.session_id)

        assert event.seq == 2
        assert [item.seq for item in loaded] == [1, 2]

    asyncio.run(run_test())


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


def test_command_policy_classifies_safe_prompt_and_deny_commands():
    policy = CommandPolicy()

    assert policy.classify("pwd").risk == CommandRisk.SAFE
    assert policy.classify("git status").risk == CommandRisk.SAFE
    assert policy.classify("rm temp.txt").risk == CommandRisk.PROMPT
    assert policy.classify("curl https://example.com").risk == CommandRisk.DENY
    assert policy.classify("curl https://example.com", network_access=True).risk == CommandRisk.PROMPT
    assert policy.classify("sudo true").risk == CommandRisk.DENY


def test_instruction_loader_reads_workspace_instruction_files(tmp_path):
    workspace = tmp_path / "workspace"
    package = workspace / "pkg"
    package.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("root agents", encoding="utf-8")
    (package / "CODECRAFT.md").write_text("package codecraft", encoding="utf-8")

    loaded = InstructionLoader().load_project_instructions(
        cwd=package,
        workspace_roots=[workspace],
    )

    assert loaded is not None
    assert "# pkg/CODECRAFT.md" in loaded
    assert "package codecraft" in loaded
    assert "# AGENTS.md" in loaded
    assert loaded.index("package codecraft") < loaded.index("root agents")


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


def test_write_file_tool_creates_and_updates_workspace_file(tmp_path):
    async def run_test() -> None:
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
        tool = WriteFileTool()
        call = ToolCall(
            call_id="call_write",
            name="write_file",
            arguments={"path": "notes/out.txt", "content": "hello", "create_parent_dirs": True},
        )

        created = await tool.arun(
            tool.args_schema.model_validate(call.arguments),
            ToolContext(context=context, call=call),
        )
        updated_call = ToolCall(
            call_id="call_write_2",
            name="write_file",
            arguments={"path": "notes/out.txt", "content": "hello again"},
        )
        updated = await tool.arun(
            tool.args_schema.model_validate(updated_call.arguments),
            ToolContext(context=context, call=updated_call),
        )

        assert (tmp_path / "notes" / "out.txt").read_text(encoding="utf-8") == "hello again"
        assert created.success is True
        assert created.data["status"] == "created"
        assert updated.success is True
        assert updated.data["status"] == "modified"
        assert "-hello" in updated.data["diff"]
        assert "+hello again" in updated.data["diff"]

    asyncio.run(run_test())


def test_write_file_tool_rejects_missing_parent_by_default(tmp_path):
    async def run_test() -> None:
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
        tool = WriteFileTool()
        call = ToolCall(
            call_id="call_write",
            name="write_file",
            arguments={"path": "missing/out.txt", "content": "hello"},
        )

        result = await tool.arun(
            tool.args_schema.model_validate(call.arguments),
            ToolContext(context=context, call=call),
        )

        assert result.success is False
        assert result.error == "parent_directory_missing"
        assert not (tmp_path / "missing" / "out.txt").exists()

    asyncio.run(run_test())


def test_apply_patch_tool_modifies_workspace_file(tmp_path):
    async def run_test() -> None:
        target = tmp_path / "note.txt"
        target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
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
        patch = """--- a/note.txt
+++ b/note.txt
@@ -1,3 +1,3 @@
 alpha
-beta
+bravo
 gamma
"""
        tool = ApplyPatchTool()
        call = ToolCall(
            call_id="call_patch",
            name="apply_patch",
            arguments={"patch": patch},
        )

        result = await tool.arun(
            tool.args_schema.model_validate(call.arguments),
            ToolContext(context=context, call=call),
        )

        assert result.success is True
        assert target.read_text(encoding="utf-8") == "alpha\nbravo\ngamma\n"
        assert result.data["modified"] == 1
        assert str(target) in result.data["changed_files"]

    asyncio.run(run_test())


def test_apply_patch_tool_rejects_workspace_escape(tmp_path):
    async def run_test() -> None:
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
        patch = """--- a/../outside.txt
+++ b/../outside.txt
@@ -1 +1 @@
-old
+new
"""
        tool = ApplyPatchTool()
        call = ToolCall(
            call_id="call_patch",
            name="apply_patch",
            arguments={"patch": patch},
        )

        result = await tool.arun(
            tool.args_schema.model_validate(call.arguments),
            ToolContext(context=context, call=call),
        )

        assert result.success is False
        assert result.error == "workspace_access_denied"

    asyncio.run(run_test())


def test_bash_tool_runs_safe_command_and_blocks_prompt_or_denied(tmp_path):
    async def run_test() -> None:
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
        tool = BashTool()
        safe_call = ToolCall(
            call_id="call_bash",
            name="bash",
            arguments={"command": "pwd"},
        )
        prompt_call = ToolCall(
            call_id="call_rm",
            name="bash",
            arguments={"command": "rm file.txt"},
        )
        denied_call = ToolCall(
            call_id="call_sudo",
            name="bash",
            arguments={"command": "sudo true"},
        )

        safe = await tool.arun(
            tool.args_schema.model_validate(safe_call.arguments),
            ToolContext(context=context, call=safe_call),
        )
        prompt = await tool.arun(
            tool.args_schema.model_validate(prompt_call.arguments),
            ToolContext(context=context, call=prompt_call),
        )
        denied = await tool.arun(
            tool.args_schema.model_validate(denied_call.arguments),
            ToolContext(context=context, call=denied_call),
        )

        assert safe.success is True
        assert safe.data["exit_code"] == 0
        assert str(tmp_path) in safe.content
        assert prompt.success is False
        assert prompt.error == "command_requires_approval"
        assert denied.success is False
        assert denied.error == "command_denied"

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


def test_openai_provider_converts_response_to_model_events(tmp_path):
    class FakeResponses:
        def __init__(self) -> None:
            self.kwargs = None

        async def create(self, **kwargs):
            self.kwargs = kwargs
            return {
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_read",
                        "name": "read_file",
                        "arguments": '{"path": "README.md"}',
                    },
                    {
                        "type": "message",
                        "content": [{"text": "done"}],
                    },
                ],
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "reasoning_tokens": 2,
                },
            }

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    async def run_test() -> None:
        config = make_config(tmp_path)
        context = TurnContext(
            session_id=config.session_id,
            thread_id=config.thread_id,
            turn_id="turn_test",
            cwd=config.cwd,
            workspace_roots=config.workspace_roots,
            model="gpt-test",
            model_provider="openai",
            approval_policy=config.approval_policy,
            sandbox_mode=config.sandbox_mode,
            network_access=config.network_access,
            available_tools=[
                ToolSpec(
                    name="read_file",
                    description="Read file.",
                    input_schema={"type": "object"},
                )
            ],
            max_steps=config.max_turn_steps,
            max_tool_output_chars=config.max_tool_output_chars,
            created_at=config.created_at,
        )
        client = FakeClient()
        provider = OpenAIProvider(client=client)

        events = [
            event
            async for event in provider.stream(
                [ModelMessage(role=ModelRole.USER, content="read")],
                context.available_tools,
                context,
            )
        ]

        assert client.responses.kwargs["model"] == "gpt-test"
        assert client.responses.kwargs["input"] == [{"role": "user", "content": "read"}]
        assert client.responses.kwargs["tools"][0]["name"] == "read_file"
        assert [event.type for event in events] == [
            ModelEventType.MESSAGE_COMPLETED,
            ModelEventType.TOOL_CALL,
            ModelEventType.TOKEN_COUNT,
            ModelEventType.COMPLETED,
        ]
        assert events[0].payload["text"] == "done"
        assert events[1].payload["arguments"] == {"path": "README.md"}
        assert events[2].payload["total_tokens"] == 17

    asyncio.run(run_test())


def test_openai_provider_serializes_tool_history_as_response_items(tmp_path):
    class FakeResponses:
        def __init__(self) -> None:
            self.kwargs = None

        async def create(self, **kwargs):
            self.kwargs = kwargs
            return {"output_text": "final"}

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    async def run_test() -> None:
        config = make_config(tmp_path)
        context = TurnContext(
            session_id=config.session_id,
            thread_id=config.thread_id,
            turn_id="turn_test",
            cwd=config.cwd,
            workspace_roots=config.workspace_roots,
            model="gpt-test",
            model_provider="openai",
            approval_policy=config.approval_policy,
            sandbox_mode=config.sandbox_mode,
            network_access=config.network_access,
            available_tools=[],
            max_steps=config.max_turn_steps,
            max_tool_output_chars=config.max_tool_output_chars,
            created_at=config.created_at,
        )
        client = FakeClient()
        provider = OpenAIProvider(client=client)

        events = [
            event
            async for event in provider.stream(
                [
                    ModelMessage(role=ModelRole.USER, content="read README"),
                    ModelMessage(
                        type=ModelMessageType.FUNCTION_CALL,
                        role=ModelRole.ASSISTANT,
                        content='{"path": "README.md"}',
                        name="read_file",
                        tool_call_id="call_read",
                        arguments={"path": "README.md"},
                    ),
                    ModelMessage(
                        type=ModelMessageType.FUNCTION_CALL_OUTPUT,
                        role=ModelRole.TOOL,
                        content="README contents",
                        name="read_file",
                        tool_call_id="call_read",
                    ),
                ],
                [],
                context,
            )
        ]

        assert client.responses.kwargs["input"] == [
            {"role": "user", "content": "read README"},
            {
                "type": "function_call",
                "call_id": "call_read",
                "name": "read_file",
                "arguments": '{"path":"README.md"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call_read",
                "output": "README contents",
            },
        ]
        assert events[0].payload["text"] == "final"

    asyncio.run(run_test())


def test_qwen_provider_uses_openai_compatible_response_conversion(tmp_path):
    class FakeResponses:
        async def create(self, **kwargs):
            return {
                "output_text": "qwen answer",
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 4,
                },
            }

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    async def run_test() -> None:
        config = make_config(tmp_path)
        context = TurnContext(
            session_id=config.session_id,
            thread_id=config.thread_id,
            turn_id="turn_test",
            cwd=config.cwd,
            workspace_roots=config.workspace_roots,
            model="qwen-plus",
            model_provider="qwen",
            approval_policy=config.approval_policy,
            sandbox_mode=config.sandbox_mode,
            network_access=config.network_access,
            available_tools=[],
            max_steps=config.max_turn_steps,
            max_tool_output_chars=config.max_tool_output_chars,
            created_at=config.created_at,
        )
        provider = QwenProvider(client=FakeClient())

        events = [
            event
            async for event in provider.stream(
                [ModelMessage(role=ModelRole.USER, content="hello")],
                [],
                context,
            )
        ]

        assert [event.type for event in events] == [
            ModelEventType.MESSAGE_COMPLETED,
            ModelEventType.TOKEN_COUNT,
            ModelEventType.COMPLETED,
        ]
        assert events[0].payload["text"] == "qwen answer"
        assert events[1].payload["total_tokens"] == 7

    asyncio.run(run_test())


def test_openai_and_qwen_share_compatible_provider_base():
    assert isinstance(OpenAIProvider(client=object()), OpenAICompatibleProvider)
    assert isinstance(QwenProvider(client=object()), OpenAICompatibleProvider)
    assert not isinstance(QwenProvider(client=object()), OpenAIProvider)


def test_qwen_provider_requires_dashscope_api_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = QwenProvider()

    with pytest.raises(Exception, match="DASHSCOPE_API_KEY"):
        provider._default_client()


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
        assert provider.calls[0][0][0].role == ModelRole.SYSTEM
        assert provider.calls[0][0][1].content == "say hello"

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
        assert [message.content for message in second_provider.calls[0][0][1:]] == [
            "first",
            "first answer",
            "second",
        ]

    asyncio.run(run_test())


def test_runtime_resume_reconstructs_tool_call_and_result_history(tmp_path):
    async def run_test() -> None:
        (tmp_path / "note.txt").write_text("resume sees tool result", encoding="utf-8")
        config = make_config(tmp_path)
        store = SessionStore(config.codecraft_home)
        first_provider = MockProvider(
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
                    payload={"text": "first answer"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        first_runtime = AgentRuntime(
            session_store=store,
            llm_providers=LLMProviderRegistry([first_provider]),
            tool_registry=ToolRegistry([ReadFileTool()]),
        )
        thread = await first_runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_one", "read note"))
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
            tool_registry=ToolRegistry([ReadFileTool()]),
        )
        resumed = await second_runtime.resume_thread(config.session_id)
        await resumed.next_event()
        await resumed.submit(SessionInput.user_message("inp_two", "continue"))
        await resumed.wait_until_idle()

        assert len(first_provider.calls) == 2
        assert len(second_provider.calls) == 1
        messages = second_provider.calls[0][0]
        assert [message.content for message in messages[1:]] == [
            "read note",
            '{"path":"note.txt"}',
            "resume sees tool result",
            "first answer",
            "continue",
        ]
        assert [message.role.value for message in messages[1:]] == [
            "user",
            "assistant",
            "tool",
            "assistant",
            "user",
        ]
        assert messages[2].type == ModelMessageType.FUNCTION_CALL
        assert messages[2].arguments == {"path": "note.txt"}
        assert messages[3].type == ModelMessageType.FUNCTION_CALL_OUTPUT

    asyncio.run(run_test())


def test_runtime_injects_system_instructions_before_conversation(tmp_path):
    async def run_test() -> None:
        (tmp_path / "AGENTS.md").write_text("Project rule: inspect files first.", encoding="utf-8")
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "answer"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path).model_copy(
            update={"user_instructions": "User rule: answer briefly."}
        )
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([ReadFileTool()]),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_one", "hello"))
        await thread.wait_until_idle()

        messages = provider.calls[0][0]
        assert messages[0].role == ModelRole.SYSTEM
        assert "<base_instructions>" in messages[0].content
        assert "Project rule: inspect files first." in messages[0].content
        assert "User rule: answer briefly." in messages[0].content
        assert "approval_policy: never" in messages[0].content
        assert messages[1].role == ModelRole.USER
        assert messages[1].content == "hello"

    asyncio.run(run_test())


def test_runtime_resume_uses_context_compaction_summary(tmp_path):
    async def run_test() -> None:
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
                payload={"text": "old user"},
            )
        )
        await store.append_event(
            RuntimeEvent(
                event_id=new_id("evt_"),
                session_id=config.session_id,
                turn_id="turn_one",
                seq=3,
                type=RuntimeEventType.CONTEXT_COMPACTED,
                payload={"summary": "old conversation summary"},
            )
        )
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "after compact"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        runtime = AgentRuntime(
            session_store=store,
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry(),
        )
        resumed = await runtime.resume_thread(config.session_id)
        await resumed.next_event()
        await resumed.submit(SessionInput.user_message("inp_two", "new user"))
        await resumed.wait_until_idle()

        messages = provider.calls[0][0]
        assert "<base_instructions>" in messages[0].content
        assert [message.content for message in messages[1:]] == [
            "old conversation summary",
            "new user",
        ]
        assert [message.role.value for message in messages[1:]] == [
            "system",
            "user",
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
        messages = provider.calls[1][0]
        assert [message.content for message in messages[1:]] == [
            "read note",
            '{"path":"note.txt"}',
            "tool loop works",
        ]
        assert messages[2].type == ModelMessageType.FUNCTION_CALL
        assert messages[3].type == ModelMessageType.FUNCTION_CALL_OUTPUT

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


def test_runtime_executes_write_file_tool_call(tmp_path):
    async def run_test() -> None:
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_write",
                        "name": "write_file",
                        "arguments": {
                            "path": "generated.txt",
                            "content": "created by runtime",
                        },
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Wrote generated.txt"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([WriteFileTool()]),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "write file"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert (tmp_path / "generated.txt").read_text(encoding="utf-8") == "created by runtime"
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
        assert finished.payload["result"]["data"]["status"] == "created"
        assert provider.calls[1][0][-1].content.startswith("created ")

    asyncio.run(run_test())


def test_runtime_emits_patch_applied_event(tmp_path):
    async def run_test() -> None:
        target = tmp_path / "note.txt"
        target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        patch = """--- a/note.txt
+++ b/note.txt
@@ -1,3 +1,3 @@
 alpha
-beta
+bravo
 gamma
"""
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_patch",
                        "name": "apply_patch",
                        "arguments": {"patch": patch},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Patched note.txt"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([ApplyPatchTool()]),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "patch file"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert target.read_text(encoding="utf-8") == "alpha\nbravo\ngamma\n"
        assert [event.type for event in snapshot.events] == [
            RuntimeEventType.SESSION_STARTED,
            RuntimeEventType.TURN_STARTED,
            RuntimeEventType.USER_MESSAGE,
            RuntimeEventType.MODEL_TOOL_CALL,
            RuntimeEventType.TOOL_CALL_STARTED,
            RuntimeEventType.TOOL_CALL_FINISHED,
            RuntimeEventType.PATCH_APPLIED,
            RuntimeEventType.ASSISTANT_MESSAGE,
            RuntimeEventType.TURN_FINISHED,
        ]
        patch_event = snapshot.events[6]
        assert patch_event.payload["modified"] == 1
        assert str(target) in patch_event.payload["changed_files"]

    asyncio.run(run_test())


def test_runtime_executes_bash_tool_call(tmp_path):
    async def run_test() -> None:
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_bash",
                        "name": "bash",
                        "arguments": {"command": "pwd"},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Ran pwd"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([BashTool()]),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "run pwd"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        finished = [
            event
            for event in snapshot.events
            if event.type == RuntimeEventType.TOOL_CALL_FINISHED
        ][0]
        assert finished.payload["result"]["success"] is True
        assert str(tmp_path) in finished.payload["result"]["data"]["stdout"]
        assert snapshot.events[-1].type == RuntimeEventType.TURN_FINISHED

    asyncio.run(run_test())


def test_tool_runner_emits_approval_events_and_runs_approved_prompt_command(tmp_path):
    async def run_test() -> None:
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_bash",
                        "name": "bash",
                        "arguments": {"command": "rm missing.txt"},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Approval path exercised"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        reviewer = AutoApprovalReviewer(approved=True, reason="test approved")
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([BashTool()]),
            approval_manager=ApprovalManager(
                policy=ApprovalPolicy.ON_REQUEST,
                reviewer=reviewer,
            ),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "remove file"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert [event.type for event in snapshot.events] == [
            RuntimeEventType.SESSION_STARTED,
            RuntimeEventType.TURN_STARTED,
            RuntimeEventType.USER_MESSAGE,
            RuntimeEventType.MODEL_TOOL_CALL,
            RuntimeEventType.TOOL_CALL_STARTED,
            RuntimeEventType.APPROVAL_REQUESTED,
            RuntimeEventType.APPROVAL_DECIDED,
            RuntimeEventType.TOOL_CALL_FINISHED,
            RuntimeEventType.ASSISTANT_MESSAGE,
            RuntimeEventType.TURN_FINISHED,
        ]
        assert reviewer.requests[0].tool_name == "bash"
        assert snapshot.events[6].payload["approved"] is True
        assert snapshot.events[7].payload["result"]["error"] == "command_failed"

    asyncio.run(run_test())


def test_tool_runner_denies_rejected_workspace_write(tmp_path):
    async def run_test() -> None:
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_write",
                        "name": "write_file",
                        "arguments": {"path": "blocked.txt", "content": "nope"},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Write was denied"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        reviewer = AutoApprovalReviewer(approved=False, reason="test denied")
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([WriteFileTool()]),
            approval_manager=ApprovalManager(
                policy=ApprovalPolicy.ON_REQUEST,
                reviewer=reviewer,
            ),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "write blocked"))
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert not (tmp_path / "blocked.txt").exists()
        assert snapshot.events[5].type == RuntimeEventType.APPROVAL_REQUESTED
        assert snapshot.events[6].payload["approved"] is False
        assert snapshot.events[7].payload["result"]["error"] == "approval_denied"
        assert snapshot.events[-1].type == RuntimeEventType.TURN_FINISHED

    asyncio.run(run_test())


def test_thread_approval_decision_allows_pending_tool_call(tmp_path):
    async def run_test() -> None:
        reviewer = ThreadApprovalReviewer()
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_write",
                        "name": "write_file",
                        "arguments": {"path": "approved.txt", "content": "yes"},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Write approved"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([WriteFileTool()]),
            approval_manager=ApprovalManager(
                policy=ApprovalPolicy.ON_REQUEST,
                reviewer=reviewer,
            ),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "write approved"))
        approval_event = await next_event_of_type(thread, RuntimeEventType.APPROVAL_REQUESTED)
        assert thread.list_pending_approvals()[0].approval_id == approval_event.payload["approval_id"]

        await thread.submit(
            SessionInput.approval_decision(
                "inp_approve",
                approval_id=approval_event.payload["approval_id"],
                approved=True,
                reason="approved in test",
            )
        )
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "yes"
        decided = [
            event
            for event in snapshot.events
            if event.type == RuntimeEventType.APPROVAL_DECIDED
        ][0]
        assert decided.payload["approved"] is True
        assert decided.payload["reviewer"] == "user"

    asyncio.run(run_test())


def test_thread_approval_decision_denies_pending_tool_call(tmp_path):
    async def run_test() -> None:
        reviewer = ThreadApprovalReviewer()
        provider = MockProvider(
            script=[
                ModelEvent(
                    type=ModelEventType.TOOL_CALL,
                    payload={
                        "call_id": "call_write",
                        "name": "write_file",
                        "arguments": {"path": "denied.txt", "content": "no"},
                    },
                ),
                ModelEvent(
                    type=ModelEventType.MESSAGE_COMPLETED,
                    payload={"text": "Write denied"},
                ),
                ModelEvent(type=ModelEventType.COMPLETED),
            ]
        )
        config = make_config(tmp_path)
        runtime = AgentRuntime(
            session_store=SessionStore(config.codecraft_home),
            llm_providers=LLMProviderRegistry([provider]),
            tool_registry=ToolRegistry([WriteFileTool()]),
            approval_manager=ApprovalManager(
                policy=ApprovalPolicy.ON_REQUEST,
                reviewer=reviewer,
            ),
        )

        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message("inp_test", "write denied"))
        approval_event = await next_event_of_type(thread, RuntimeEventType.APPROVAL_REQUESTED)
        await thread.submit(
            SessionInput.approval_decision(
                "inp_deny",
                approval_id=approval_event.payload["approval_id"],
                approved=False,
                reason="denied in test",
            )
        )
        await thread.wait_until_idle()
        snapshot = await thread.read_snapshot()

        assert not (tmp_path / "denied.txt").exists()
        finished = [
            event
            for event in snapshot.events
            if event.type == RuntimeEventType.TOOL_CALL_FINISHED
        ][0]
        assert finished.payload["result"]["error"] == "approval_denied"

    asyncio.run(run_test())
