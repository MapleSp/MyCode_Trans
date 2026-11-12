"""内存 TTL 缓存。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """线程安全的轻量热点缓存。"""

    def __init__(self, default_ttl: int = 900, max_items: int = 512) -> None:
        self.default_ttl = default_ttl
        self.max_items = max_items
        self._items: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if not entry:
                return None
            if entry.expires_at <= now:
                self._items.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            if len(self._items) >= self.max_items:
                expired = [item_key for item_key, item in self._items.items() if item.expires_at <= time.monotonic()]
                for item_key in expired:
                    self._items.pop(item_key, None)
            if len(self._items) >= self.max_items:
                oldest_key = min(self._items, key=lambda item_key: self._items[item_key].expires_at)
                self._items.pop(oldest_key, None)
            self._items[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + (ttl or self.default_ttl),
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._items)
