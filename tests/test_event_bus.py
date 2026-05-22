from __future__ import annotations

import pytest

from codecraft.core.event_bus import EventBus
from codecraft.schema.event import ThoughtEvent


@pytest.mark.anyio
async def test_event_bus_emits_to_async_handlers_in_order():
    bus = EventBus()
    calls: list[tuple[str, str]] = []

    async def first(event):
        calls.append(("first", event.type))

    async def second(event):
        calls.append(("second", event.type))

    bus.subscribe(first)
    bus.subscribe(second)

    await bus.emit(ThoughtEvent(thought="inspect"))

    assert calls == [
        ("first", "thought"),
        ("second", "thought"),
    ]


@pytest.mark.anyio
async def test_event_bus_rejects_sync_handlers():
    bus = EventBus()

    def sync_handler(event):
        return None

    bus.subscribe(sync_handler)

    with pytest.raises(TypeError, match="async callable"):
        await bus.emit(ThoughtEvent(thought="inspect"))
