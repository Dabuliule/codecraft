from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import isawaitable

from codecraft.schema.event import RuntimeEvent

EventHandler = Callable[[RuntimeEvent], Awaitable[None]]


class EventBus:
    """
    Minimal async event bus for runtime events.

    Handlers are called in subscription order. Handler exceptions propagate to
    the caller so orchestration code can fail fast instead of hiding side
    effects that did not run.
    """

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(
            self,
            handler: EventHandler,
    ) -> None:
        self._handlers.append(handler)

    async def emit(
            self,
            event: RuntimeEvent,
    ) -> None:
        for handler in list(self._handlers):
            result = handler(event)

            if not isawaitable(result):
                raise TypeError(
                    "EventBus handler must be an async callable"
                )

            await result
