from __future__ import annotations

from importlib import resources


BASE_INSTRUCTIONS = (
    resources.files(__package__)
    .joinpath("resources", "BASE_INSTRUCTIONS.md")
    .read_text(encoding="utf-8")
)
