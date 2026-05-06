from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from contextvars import ContextVar
from typing import Any, Callable, Generator, Optional


@dataclass(frozen=True)
class TraceContext:
    trace_id: Optional[str] = None
    step: Optional[int] = None
    component: Optional[str] = None


_TRACE_CONTEXT: ContextVar[Optional[TraceContext]] = ContextVar("trace_context", default=None)


def get_trace_context() -> TraceContext:
    ctx = _TRACE_CONTEXT.get()
    if ctx is None:
        return TraceContext()
    return ctx


def _merge_context(
    current: TraceContext,
    *,
    trace_id: Optional[str] = None,
    step: Optional[int] = None,
    component: Optional[str] = None,
) -> TraceContext:
    return TraceContext(
        trace_id=trace_id if trace_id is not None else current.trace_id,
        step=step if step is not None else current.step,
        component=component if component is not None else current.component,
    )


@contextmanager
def trace_scope(
    *,
    trace_id: Optional[str] = None,
    step: Optional[int] = None,
    component: Optional[str] = None,
) -> Generator[TraceContext, None, None]:
    current = get_trace_context()
    next_ctx = _merge_context(
        current,
        trace_id=trace_id,
        step=step,
        component=component,
    )
    token = _TRACE_CONTEXT.set(next_ctx)
    try:
        yield next_ctx
    finally:
        _TRACE_CONTEXT.reset(token)


def traced(
    name: Optional[str] = None,
    *,
    component: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        import functools
        from .trace import TraceLogger

        event_base = name or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_scope(component=component):
                TraceLogger.log(f"{event_base}.start")
                try:
                    result = func(*args, **kwargs)
                except Exception as exc:
                    TraceLogger.log(
                        f"{event_base}.error",
                        {"error": str(exc)},
                        level="ERROR",
                    )
                    raise
                TraceLogger.log(
                    f"{event_base}.success",
                    {"result_type": type(result).__name__},
                )
                return result

        return wrapper

    return decorator

