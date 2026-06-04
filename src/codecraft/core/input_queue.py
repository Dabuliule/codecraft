from __future__ import annotations

import asyncio

from codecraft.schema.input import SessionInput


class InputQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[SessionInput] = asyncio.Queue()

    async def put(self, input: SessionInput) -> None:
        await self._queue.put(input)

    async def get(self) -> SessionInput:
        return await self._queue.get()

    def empty(self) -> bool:
        return self._queue.empty()
