from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def sanitize_text(value: str) -> str:
    return value.encode("utf-8", errors="replace").decode("utf-8")


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)

    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]

    if isinstance(value, tuple):
        return [sanitize_json_value(item) for item in value]

    if isinstance(value, Mapping):
        return {
            sanitize_text(str(key)): sanitize_json_value(item)
            for key, item in value.items()
        }

    return value
