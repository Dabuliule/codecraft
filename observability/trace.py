import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from observability.context import get_trace_context


class TraceLogger:
    _LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
    _enabled: Optional[bool] = None
    _level: Optional[str] = None

    @classmethod
    def configure(cls, *, enabled: Optional[bool] = None, level: Optional[str] = None) -> None:
        if enabled is not None:
            cls._enabled = enabled
        if level:
            cls._level = level.upper()

    @classmethod
    def _ensure_config(cls) -> None:
        if cls._enabled is None:
            raw = os.getenv("TRACE_ENABLED", "1").strip().lower()
            cls._enabled = raw not in {"0", "false", "no", "off"}
        if cls._level is None:
            cls._level = os.getenv("TRACE_LEVEL", "INFO").strip().upper()

    @classmethod
    def _should_log(cls, level: str) -> bool:
        cls._ensure_config()
        if not cls._enabled:
            return False
        current = cls._LEVELS.get(cls._level or "INFO", 20)
        incoming = cls._LEVELS.get(level.upper(), 20)
        return incoming >= current

    @classmethod
    def log(
        cls,
        event: str,
        data: Optional[Dict[str, Any]] = None,
        *,
        level: str = "INFO",
    ) -> None:
        if not cls._should_log(level):
            return

        ctx = get_trace_context()
        payload: Dict[str, Any] = {
            "ts": datetime.now().astimezone().isoformat(),
            "level": level.upper(),
            "event": event,
        }
        if ctx.trace_id:
            payload["trace_id"] = ctx.trace_id
        if ctx.step is not None:
            payload["step"] = ctx.step
        if ctx.component:
            payload["component"] = ctx.component
        if data is not None:
            payload["data"] = data

        print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)
