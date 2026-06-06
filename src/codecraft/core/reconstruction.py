from __future__ import annotations

from codecraft.core.conversation import Conversation
from codecraft.schema.event import RuntimeEvent, RuntimeEventType


def reconstruct_conversation(events: list[RuntimeEvent]) -> Conversation:
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
                content = str(result.get("content", ""))
            conversation.append_tool_result(call_id, name, content)

        elif event.type == RuntimeEventType.CONTEXT_COMPACTED:
            summary = event.payload.get("summary")
            if isinstance(summary, str) and summary:
                conversation = Conversation()
                conversation.append_summary(summary)

    return conversation
