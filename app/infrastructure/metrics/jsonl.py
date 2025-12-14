from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


class MetricsClient:
    def __init__(self):
        self._logger = logging.getLogger("metrics.actions")

    def configure(self, logger: logging.Logger | None = None) -> None:
        if logger:
            self._logger = logger

    def _emit(self, action: str, duration_ms: float, success: bool, *, source: str | None, extra: dict | None) -> None:
        payload: dict[str, Any] = {
            "ts": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "action": action,
            "duration_ms": round(duration_ms, 3),
            "success": success,
        }
        if source:
            payload["source"] = source
        if extra:
            payload.update(extra)
        self._logger.info(json.dumps(payload, ensure_ascii=False))

    @contextmanager
    def span(self, action: str, *, source: str | None = None, extra: dict | None = None):
        start = time.perf_counter()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            duration = (time.perf_counter() - start) * 1000
            self._emit(action, duration, success, source=source, extra=extra)

    @asynccontextmanager
    async def span_async(self, action: str, *, source: str | None = None, extra: dict | None = None):
        start = time.perf_counter()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            duration = (time.perf_counter() - start) * 1000
            self._emit(action, duration, success, source=source, extra=extra)

    def wrap_async(
        self,
        action: str,
        *,
        source: str | None = None,
        extra_fn: Callable[[tuple, dict], dict | None] | None = None,
    ):
        def decorator(func: Callable[..., Awaitable[T]]):
            async def wrapper(*args, **kwargs):
                extra = extra_fn(*args, **kwargs) if extra_fn else None
                async with self.span_async(action, source=source, extra=extra):
                    return await func(*args, **kwargs)

            return wrapper

        return decorator

    def wrap_sync(
        self,
        action: str,
        *,
        source: str | None = None,
        extra_fn: Callable[[tuple, dict], dict | None] | None = None,
    ):
        def decorator(func: Callable[..., T]):
            def wrapper(*args, **kwargs):
                extra = extra_fn(*args, **kwargs) if extra_fn else None
                with self.span(action, source=source, extra=extra):
                    return func(*args, **kwargs)

            return wrapper

        return decorator


metrics = MetricsClient()

