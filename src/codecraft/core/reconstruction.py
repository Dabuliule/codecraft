from __future__ import annotations

from codecraft.core.conversation import Conversation
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.tool import ToolResult


def reconstruct_conversation(events: list[RuntimeEvent]) -> Conversation:
    """从 RuntimeEvent 日志重建可继续发送给模型的 conversation。

    恢复会话时不会直接序列化 Conversation，而是根据公开事件反推上下文。
    这样事件日志既是审计记录，也是恢复状态的唯一来源。
    """
    conversation = Conversation()

    for event in events:
        if event.type == RuntimeEventType.USER_MESSAGE:
            conversation.append_user_message(str(event.payload.get("text", "")))

        elif event.type == RuntimeEventType.ASSISTANT_MESSAGE:
            conversation.append_assistant_message(str(event.payload.get("text", "")))

        elif event.type == RuntimeEventType.MODEL_TOOL_CALL:
            call_id = str(event.payload.get("call_id", ""))
            name = str(event.payload.get("name", ""))
            arguments = event.payload.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            conversation.append_model_tool_call(call_id, name, arguments)

        elif event.type == RuntimeEventType.TOOL_CALL_FINISHED:
            call_id = str(event.payload.get("call_id", ""))
            name = str(event.payload.get("name", ""))
            result = event.payload.get("result")
            content = ""
            if isinstance(result, dict):
                content = ToolResult.model_validate(result).model_content()
            conversation.append_tool_result(call_id, name, content)

        elif event.type == RuntimeEventType.CONTEXT_COMPACTED:
            summary = event.payload.get("summary")
            if isinstance(summary, str) and summary:
                # 压缩事件代表旧上下文被摘要替换，之前的消息不再进入模型上下文。
                conversation = Conversation()
                conversation.append_summary(summary)

    return conversation
