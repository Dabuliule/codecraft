from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Generator, Optional


@dataclass(frozen=True)
class TraceContext:
    trace_id: Optional[str] = None
    component: Optional[str] = None


_TRACE_CONTEXT: ContextVar[TraceContext] = ContextVar(
    "trace_context",
    default=TraceContext(),
)


def get_trace_context() -> TraceContext:
    return _TRACE_CONTEXT.get()


@contextmanager
def trace_scope(
        *,
        trace_id: Optional[str] = None,
        component: Optional[str] = None,
) -> Generator[TraceContext, None, None]:
    current = get_trace_context()

    next_ctx = TraceContext(
        trace_id=trace_id or current.trace_id,
        component=component or current.component,
    )

    token = _TRACE_CONTEXT.set(next_ctx)

    try:
        yield next_ctx
    finally:
        _TRACE_CONTEXT.reset(token)
