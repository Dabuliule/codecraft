from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional

from observability.context import trace_scope
from observability.trace import TraceLogger


class Middleware(ABC):
    @abstractmethod
    def process(self, next_call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


class Pipeline:
    def __init__(self, middlewares: Optional[List[Middleware]] = None) -> None:
        self._middlewares = middlewares or []

    def run(self, target: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        def call(index: int, *call_args: Any, **call_kwargs: Any) -> Any:
            if index >= len(self._middlewares):
                return target(*call_args, **call_kwargs)
            middleware = self._middlewares[index]
            return middleware.process(
                lambda *next_args, **next_kwargs: call(
                    index + 1, *next_args, **next_kwargs
                ),
                *call_args,
                **call_kwargs,
            )

        return call(0, *args, **kwargs)


class TraceMiddleware(Middleware):
    def __init__(self, component: str = "executor") -> None:
        self.component = component

    def process(self, next_call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        state = args[0] if args else kwargs.get("state")
        trace_id = getattr(state, "trace_id", None)
        step = getattr(state, "current_step", None)

        with trace_scope(trace_id=trace_id, step=step, component=self.component):
            TraceLogger.log("executor.step.start", {"step": step})
            try:
                result = next_call(*args, **kwargs)
            except Exception as exc:
                TraceLogger.log(
                    "executor.step.error",
                    {"error": str(exc)},
                    level="ERROR",
                )
                raise
            TraceLogger.log(
                "executor.step.success",
                {"result_type": type(result).__name__},
            )
            return result

