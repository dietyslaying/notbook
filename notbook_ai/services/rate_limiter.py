"""Simple per-user sliding-window rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_per_minute: int):
        self._max = max(1, int(max_per_minute))
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.time()
        window = self._hits[user_id]
        while window and now - window[0] >= 60.0:
            window.popleft()
        if len(window) >= self._max:
            return False
        window.append(now)
        return True

    def retry_after_seconds(self, user_id: int) -> int:
        window = self._hits.get(user_id)
        if not window:
            return 0
        oldest = window[0]
        return max(1, int(60 - (time.time() - oldest)) + 1)
