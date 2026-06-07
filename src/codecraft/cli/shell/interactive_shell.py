from __future__ import annotations

from codecraft.cli.shell.context import ShellContext
from codecraft.cli.shell.input_controller import InputController
from codecraft.cli.shell.runner import shutdown_thread, submit_user_message


class InteractiveShell:
    def __init__(self, context: ShellContext, input_controller: InputController) -> None:
        self.context = context
        self.input_controller = input_controller
        self.running = True

    async def run(self, initial_prompt: str | None = None, *, show_welcome: bool = True) -> int:
        if show_welcome:
            self.context.renderer.render_welcome(self.context.config)

        if initial_prompt:
            exit_code = await self.submit_user_message(initial_prompt)
            if exit_code:
                return exit_code

        while self.running:
            try:
                text = (await self.input_controller.read()).strip()
            except (EOFError, KeyboardInterrupt):
                await self.shutdown()
                self.context.console.print()
                return 0

            if not text:
                continue
            if text in {"/exit", "/quit", "exit", "quit"}:
                await self.shutdown()
                return 0
            if self.context.slash_router.is_slash_command(text):
                result = await self.context.slash_router.handle(text, self.context)
                if result.should_exit:
                    await self.shutdown()
                    return result.exit_code
                continue

            exit_code = await self.submit_user_message(text)
            if exit_code:
                return exit_code
        return 0

    async def submit_user_message(self, text: str) -> int:
        return await submit_user_message(self.context.thread, self.context.renderer, text)

    async def shutdown(self) -> None:
        self.running = False
        await shutdown_thread(self.context.thread)
