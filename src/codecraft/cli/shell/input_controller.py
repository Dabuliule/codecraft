from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from codecraft.cli.shell.completer import make_slash_completer


class InputController:
    def __init__(self, history_path: Path, *, multiline: bool = True) -> None:
        self.history_path = history_path
        self.multiline = multiline
        self._prompt_session = self._build_prompt_session()

    async def read(self) -> str:
        if self._prompt_session is not None:
            return await self._prompt_session.prompt_async("› ")
        return await asyncio.to_thread(input, "› ")

    async def ask(self, prompt: str) -> str:
        if self._prompt_session is not None:
            return await self._prompt_session.prompt_async(prompt, multiline=False)
        return await asyncio.to_thread(input, prompt)

    def _build_prompt_session(self):
        if not sys.stdin.isatty():
            return None
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.history import FileHistory
            from prompt_toolkit.key_binding import KeyBindings
        except ModuleNotFoundError:
            return None

        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        key_bindings = KeyBindings()

        @key_bindings.add("enter")
        def _(event) -> None:
            event.current_buffer.validate_and_handle()

        @key_bindings.add("c-j")
        def _(event) -> None:
            event.current_buffer.insert_text("\n")

        return PromptSession(
            history=FileHistory(str(self.history_path)),
            completer=make_slash_completer(),
            multiline=self.multiline,
            key_bindings=key_bindings,
        )
