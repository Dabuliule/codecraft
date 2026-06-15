from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
import json
from typing import Any

from pydantic import BaseModel, Field

from codecraft.core.ids import new_id
from codecraft.llm.messages import ModelMessage, ModelMessageType, ModelRole


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
    """模型上下文中的对话历史。

    内部用 ConversationItem 保存更丰富的元数据；真正请求模型前，再转换成
    provider 能理解的 ModelMessage。
    """

    items: list[ConversationItem] = Field(default_factory=list)

    def append(self, item: ConversationItem) -> None:
        self.items.append(item)

    def append_user_message(self, content: str) -> ConversationItem:
        """追加普通用户消息。"""
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

    def append_model_tool_call(
        self,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> ConversationItem:
        """记录 assistant 发起的 tool call。

        content 保存稳定的 JSON 字符串，metadata 保存结构化 arguments，方便
        后续适配 Responses API 和 Chat Completions API。
        """
        item = ConversationItem(
            item_id=new_id("item_"),
            role=ConversationRole.ASSISTANT,
            content=json.dumps(
                arguments, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
            tool_call_id=tool_call_id,
            name=name,
            metadata={
                "type": ModelMessageType.FUNCTION_CALL.value,
                "arguments": arguments,
            },
        )
        self.append(item)
        return item

    def append_tool_result(
        self, tool_call_id: str, name: str, content: str
    ) -> ConversationItem:
        """追加 tool call 的执行结果。"""
        item = ConversationItem(
            item_id=new_id("item_"),
            role=ConversationRole.TOOL,
            content=content,
            tool_call_id=tool_call_id,
            name=name,
        )
        self.append(item)
        return item

    def append_summary(self, content: str) -> ConversationItem:
        """追加压缩后的历史摘要。"""
        item = ConversationItem(
            item_id=new_id("item_"),
            role=ConversationRole.SUMMARY,
            content=content,
        )
        self.append(item)
        return item

    def build_model_messages(self) -> list[ModelMessage]:
        """把内部 conversation item 转成模型请求消息。"""
        messages: list[ModelMessage] = []
        for item in self.items:
            role = self._to_model_role(item.role)
            if role is None:
                continue

            message_type = ModelMessageType(
                item.metadata.get("type", ModelMessageType.MESSAGE)
            )
            arguments = item.metadata.get("arguments")
            if not isinstance(arguments, dict):
                arguments = None

            if item.role == ConversationRole.TOOL:
                message_type = ModelMessageType.FUNCTION_CALL_OUTPUT

            messages.append(
                ModelMessage(
                    type=message_type,
                    role=role,
                    content=item.content,
                    name=item.name,
                    tool_call_id=item.tool_call_id,
                    arguments=arguments,
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
