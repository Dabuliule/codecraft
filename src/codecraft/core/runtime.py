from __future__ import annotations

from pathlib import Path

from codecraft.core.conversation import Conversation
from codecraft.core.event_bus import EventBus
from codecraft.core.session import Session
from codecraft.core.session_store import SessionStore
from codecraft.core.thread import AgentThread
from codecraft.llm.registry import LLMProviderRegistry
from codecraft.schema.event import RuntimeEventType
from codecraft.schema.session import SessionConfig, SessionSummary
from codecraft.tool.registry import ToolRegistry


class AgentRuntime:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        llm_providers: LLMProviderRegistry,
        tool_registry: ToolRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self.session_store = session_store
        self.llm_providers = llm_providers
        self.tool_registry = tool_registry
        self.event_bus = event_bus

    async def create_thread(self, config: SessionConfig) -> AgentThread:
        await self.session_store.create_session(config)
        session = Session(
            config=config,
            session_store=self.session_store,
            llm_provider=self.llm_providers.get(config.model_provider),
            tool_registry=self.tool_registry,
            event_bus=self.event_bus,
        )
        thread = AgentThread(session)
        await session.emit(
            RuntimeEventType.SESSION_STARTED,
            {"config": config.model_dump(mode="json")},
        )
        return thread

    async def resume_thread(self, session_id: str) -> AgentThread:
        snapshot = await self.session_store.resume(session_id)
        conversation = Conversation()
        for event in snapshot.events:
            if event.type == RuntimeEventType.USER_MESSAGE:
                conversation.append_user_message(str(event.payload.get("text", "")))
            elif event.type == RuntimeEventType.ASSISTANT_MESSAGE:
                conversation.append_assistant_message(str(event.payload.get("text", "")))

        session = Session(
            config=snapshot.config,
            session_store=self.session_store,
            llm_provider=self.llm_providers.get(snapshot.config.model_provider),
            tool_registry=self.tool_registry,
            event_bus=self.event_bus,
            conversation=conversation,
            seq=snapshot.events[-1].seq if snapshot.events else 0,
        )
        thread = AgentThread(session)
        await session.emit(RuntimeEventType.SESSION_RESTORED)
        return thread

    async def resume_last(self, cwd: Path | None = None) -> AgentThread:
        snapshot = await self.session_store.resume_last(cwd=cwd)
        return await self.resume_thread(snapshot.config.session_id)

    async def list_sessions(self, cwd: Path | None = None) -> list[SessionSummary]:
        return await self.session_store.list_sessions(cwd=cwd)
