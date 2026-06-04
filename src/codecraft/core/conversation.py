from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from codecraft.core.ids import new_id
from codecraft.llm.messages import ModelMessage, ModelRole


class ConversationRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SUMMARY = "summary"


class ConversationItem(BaseModel):
    item_id: str
    role: ConversationRole
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Conversation(BaseModel):
    items: list[ConversationItem] = Field(default_factory=list)

    def append(self, item: ConversationItem) -> None:
        self.items.append(item)

    def append_user_message(self, content: str) -> ConversationItem:
        item = ConversationItem(
            item_id=new_id("item_"),
            role=ConversationRole.USER,
            content=content,
        )
        self.append(item)
        return item

    def append_assistant_message(self, content: str) -> ConversationItem:
        item = ConversationItem(
            item_id=new_id("item_"),
            role=ConversationRole.ASSISTANT,
            content=content,
        )
        self.append(item)
        return item

    def append_model_tool_call(self, tool_call_id: str, name: str, content: str) -> ConversationItem:
        item = ConversationItem(
            item_id=new_id("item_"),
            role=ConversationRole.ASSISTANT,
            content=content,
            tool_call_id=tool_call_id,
            name=name,
        )
        self.append(item)
        return item

    def append_tool_result(self, tool_call_id: str, name: str, content: str) -> ConversationItem:
        item = ConversationItem(
            item_id=new_id("item_"),
            role=ConversationRole.TOOL,
            content=content,
            tool_call_id=tool_call_id,
            name=name,
        )
        self.append(item)
        return item

    def build_model_messages(self) -> list[ModelMessage]:
        messages: list[ModelMessage] = []
        for item in self.items:
            role = self._to_model_role(item.role)
            if role is None:
                continue

            messages.append(
                ModelMessage(
                    role=role,
                    content=item.content,
                    name=item.name,
                    tool_call_id=item.tool_call_id,
                    metadata=item.metadata,
                )
            )

        return messages

    def last_user_message(self) -> ConversationItem | None:
        for item in reversed(self.items):
            if item.role == ConversationRole.USER:
                return item
        return None

    @staticmethod
    def _to_model_role(role: ConversationRole) -> ModelRole | None:
        if role == ConversationRole.SUMMARY:
            return ModelRole.SYSTEM
        if role == ConversationRole.SYSTEM:
            return ModelRole.SYSTEM
        if role == ConversationRole.USER:
            return ModelRole.USER
        if role == ConversationRole.ASSISTANT:
            return ModelRole.ASSISTANT
        if role == ConversationRole.TOOL:
            return ModelRole.TOOL
        return None
