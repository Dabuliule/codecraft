from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


_SENSITIVE_KEY = re.compile(
    r"(^|[_-])(api[_-]?key|authorization|cookie|credential|password|secret|token)([_-]|$)",
    re.IGNORECASE,
)
REDACTED = "[REDACTED]"


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


def redact_sensitive_json_value(value: Any) -> Any:
    """按字段名递归脱敏持久化事件中的常见凭据。"""
    if isinstance(value, list):
        return [redact_sensitive_json_value(item) for item in value]

    if isinstance(value, tuple):
        return [redact_sensitive_json_value(item) for item in value]

    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = sanitize_text(str(key))
            redacted[key_text] = (
                REDACTED
                if _is_sensitive_key(key_text)
                else redact_sensitive_json_value(item)
            )
        return redacted

    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    if normalized.endswith(("_env", "_field", "_name")):
        return False
    return _SENSITIVE_KEY.search(normalized) is not None
