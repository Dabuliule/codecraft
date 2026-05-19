from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Optional

from agent_runtime.observability.context import trace_scope
from agent_runtime.observability.trace import TraceLogger


def _safe(obj: Any) -> Any:
    try:
        repr_str = repr(obj)

        # 防止日志爆炸
        if len(repr_str) > 1000:
            return repr_str[:1000] + "...(truncated)"

        return repr_str

    except Exception:
        return f"<unserializable {type(obj).__name__}>"


def traced(
        name: Optional[str] = None,
        *,
        component: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        event = name or func.__qualname__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with trace_scope(component=component):
                    TraceLogger.log(
                        f"{event}.start",
                        {
                            "args": [_safe(a) for a in args],
                            "kwargs": {k: _safe(v) for k, v in kwargs.items()},
                        },
                    )

                    try:
                        result = await func(*args, **kwargs)
                    except Exception as e:
                        TraceLogger.log(
                            f"{event}.error",
                            {"error": str(e)},
                            level="ERROR",
                        )
                        raise

                    TraceLogger.log(
                        f"{event}.success",
                        {
                            "result": _safe(result),
                        },
                    )

                    return result

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_scope(component=component):
                TraceLogger.log(
                    f"{event}.start",
                    {
                        "args": [_safe(a) for a in args],
                        "kwargs": {k: _safe(v) for k, v in kwargs.items()},
                    },
                )

                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    TraceLogger.log(
                        f"{event}.error",
                        {"error": str(e)},
                        level="ERROR",
                    )
                    raise

                TraceLogger.log(
                    f"{event}.success",
                    {
                        "result": _safe(result),
                    },
                )

                return result

        return wrapper

    return decorator
