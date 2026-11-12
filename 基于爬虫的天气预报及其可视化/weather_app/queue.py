"""有界并发队列与同城请求合并。"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar

from .errors import QueueBusyError, UpstreamError


ResultT = TypeVar("ResultT")


class WeatherTaskQueue:
    """限制并发和排队数量，并避免相同城市被重复抓取。"""

    def __init__(self, workers: int = 4, capacity: int = 32) -> None:
        self.workers = workers
        self.capacity = capacity
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="weather-worker",
        )
        self._slots = threading.BoundedSemaphore(capacity)
        self._inflight: dict[str, Future] = {}
        self._lock = threading.RLock()

    def run(
        self,
        key: str,
        task: Callable[[], ResultT],
        *,
        timeout: float,
    ) -> tuple[ResultT, bool]:
        """返回任务结果及是否为合并请求。"""

        with self._lock:
            existing = self._inflight.get(key)
            if existing:
                future = existing
                coalesced = True
            else:
                if not self._slots.acquire(blocking=False):
                    raise QueueBusyError()
                future = self._executor.submit(self._execute, key, task)
                self._inflight[key] = future
                coalesced = False

        try:
            return future.result(timeout=timeout), coalesced
        except FutureTimeoutError as exc:
            raise UpstreamError("天气数据获取超时，请稍后重试", details={"timeout": timeout}) from exc

    def _execute(self, key: str, task: Callable[[], ResultT]) -> ResultT:
        try:
            return task()
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            self._slots.release()

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._inflight)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
