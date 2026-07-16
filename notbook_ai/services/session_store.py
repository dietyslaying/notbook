"""In-memory multi-page content sessions for pagination callbacks."""

from __future__ import annotations

import time
from typing import Optional

from interfaces import ContentSession


class SessionStore:
    def __init__(self, ttl_seconds: int = 3600, max_sessions: int = 1000):
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._data: dict[str, tuple[ContentSession, float]] = {}

    def put(self, session: ContentSession) -> None:
        self._evict()
        self._data[session.concept_id] = (session, time.time())
        if len(self._data) > self._max:
            # Drop oldest
            oldest_key = min(self._data.items(), key=lambda kv: kv[1][1])[0]
            self._data.pop(oldest_key, None)

    def get(self, concept_id: str) -> Optional[ContentSession]:
        item = self._data.get(concept_id)
        if not item:
            return None
        session, ts = item
        if time.time() - ts > self._ttl:
            self._data.pop(concept_id, None)
            return None
        return session

    def _evict(self) -> None:
        now = time.time()
        expired = [k for k, (_, ts) in self._data.items() if now - ts > self._ttl]
        for k in expired:
            self._data.pop(k, None)


# Process-wide store for callback navigation
session_store = SessionStore()
