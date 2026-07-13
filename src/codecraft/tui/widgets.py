from __future__ import annotations

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.text import Text
from textual.widgets import Static


class MessageBlock(Static):
    def __init__(self, role: str, text: str = "") -> None:
        super().__init__(classes=role.casefold())
        self.role = role
        self.text = text

    def set_text(self, text: str) -> None:
        self.text = text
        self.refresh(layout=True)

    def render(self) -> RenderableType:
        role_style = {
            "User": "bold #7bdff2",
            "Assistant": "bold #72d6a0",
            "Error": "bold #ef6b73",
        }.get(self.role, "bold #d7a95b")
        body: RenderableType = (
            Markdown(self.text) if self.role == "Assistant" else Text(self.text)
        )
        return Group(Text(self.role, style=role_style), body)
