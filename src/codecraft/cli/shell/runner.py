from __future__ import annotations

import asyncio

from codecraft.core.ids import new_id
from codecraft.core.thread import AgentThread
from codecraft.cli.ui.event_renderer import RuntimeEventRenderer
from codecraft.schema.event import RuntimeEventType
from codecraft.schema.input import SessionInput


async def submit_user_message(
    thread: AgentThread,
    renderer: RuntimeEventRenderer,
    text: str,
) -> int:
    await thread.submit(SessionInput.user_message(new_id("inp_"), text))
    return await consume_turn(thread, renderer)


async def consume_turn(thread: AgentThread, renderer: RuntimeEventRenderer) -> int:
    try:
        while True:
            event = await thread.next_event()
            if event.type == RuntimeEventType.APPROVAL_REQUESTED:
                decision = await renderer.request_approval(event)
                await thread.submit(decision)
                continue

            await renderer.render(event)

            if event.type == RuntimeEventType.TURN_FINISHED:
                renderer.ensure_newline()
                await thread.wait_until_idle()
                return 0
            if event.type == RuntimeEventType.TURN_ABORTED:
                renderer.ensure_newline()
                await thread.wait_until_idle()
                return 1
    except KeyboardInterrupt:
        await shutdown_thread(thread)
        raise


async def shutdown_thread(thread: AgentThread) -> None:
    for approval in thread.list_pending_approvals():
        await thread.submit(
            SessionInput.approval_decision(
                new_id("inp_"),
                approval_id=approval.approval_id,
                approved=False,
                reason="interrupted by CLI",
            )
        )
    await thread.interrupt("interrupted by CLI")
    await thread.close()
    try:
        await asyncio.wait_for(thread.wait_until_idle(), timeout=1)
    except TimeoutError:
        return
