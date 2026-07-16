"""Bounded TTL cache (in-memory)."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional


class CacheManager:
    def __init__(self, ttl: int, max_entries: int = 500):
        self._ttl = max(1, int(ttl))
        self._max = max(1, int(max_entries))
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        item = self._cache.get(key)
        if item is None:
            return None
        data, ts = item
        if time.time() - ts >= self._ttl:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return data

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, time.time())
        while len(self._cache) > self._max:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()
