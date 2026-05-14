import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from observability.context import get_trace_context


class TraceLogger:
    _LEVELS = {
        "DEBUG": 10,
        "INFO": 20,
        "WARN": 30,
        "ERROR": 40,
    }

    @classmethod
    def _enabled(cls) -> bool:
        raw = os.getenv("TRACE_ENABLED", "1").lower()
        return raw not in {"0", "false", "off"}

    @classmethod
    def _current_level(cls) -> int:
        level = os.getenv("TRACE_LEVEL", "INFO").upper()
        return cls._LEVELS.get(level, 20)

    @classmethod
    def _should_log(cls, level: str) -> bool:
        if not cls._enabled():
            return False

        return cls._LEVELS.get(level, 20) >= cls._current_level()

    @classmethod
    def log(
            cls,
            event: str,
            data: Optional[Dict[str, Any]] = None,
            *,
            level: str = "INFO",
    ) -> None:
        level = level.upper()

        if not cls._should_log(level):
            return

        ctx = get_trace_context()

        payload: Dict[str, Any] = {
            "ts": datetime.now().astimezone().isoformat(),
            "level": level,
            "event": event,
        }

        if ctx.trace_id:
            payload["trace_id"] = ctx.trace_id

        if ctx.component:
            payload["component"] = ctx.component

        if data:
            payload["data"] = data

        print(json.dumps(payload, default=str), flush=True)
