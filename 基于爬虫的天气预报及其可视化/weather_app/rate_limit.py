"""基于滑动窗口的 API 限流。"""

from __future__ import annotations

import threading
import time
from collections import deque
from functools import wraps
from typing import Any, Callable, TypeVar

from flask import current_app, request

from .errors import ApiError


ViewT = TypeVar("ViewT", bound=Callable[..., Any])


class RateLimiter:
    """按客户端与路由维度记录最近请求时间。"""

    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> tuple[int, int, int]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            remaining = max(0, limit - len(bucket))
            if len(bucket) >= limit:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                raise ApiError(
                    "请求过于频繁，请稍后再试",
                    code="RATE_LIMITED",
                    status_code=429,
                    details={"retry_after": retry_after},
                )
            bucket.append(now)
            if len(self._events) > 5000:
                self._cleanup(cutoff)
            return remaining - 1, limit, self.window_seconds

    def _cleanup(self, cutoff: float) -> None:
        empty_keys = [key for key, bucket in self._events.items() if not bucket or bucket[-1] <= cutoff]
        for key in empty_keys:
            self._events.pop(key, None)


def rate_limited(endpoint: str, limit_key: str) -> Callable[[ViewT], ViewT]:
    def decorator(view: ViewT) -> ViewT:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            limiter: RateLimiter = current_app.extensions["rate_limiter"]
            limit = int(current_app.config.get(limit_key, 30))
            # 限流必须使用服务器侧可验证的地址，不能信任客户端自行提交的标识。
            client = request.remote_addr or "unknown"
            remaining, total, window = limiter.check(f"{endpoint}:{client}", limit)
            response = view(*args, **kwargs)
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(total)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Window"] = str(window)
            return response

        return wrapped

    return decorator
