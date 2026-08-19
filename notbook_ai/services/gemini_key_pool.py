"""Shared Gemini API key pool with rotate-on-error + cooldowns.

Used by chat generation and embeddings so free-tier daily/RPM limits
on one key do not pin the whole process to that key forever.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Optional

from config import config

logger = logging.getLogger(__name__)

# Cooldowns (seconds) after failures
_COOLDOWN_RPM = 35.0          # short rate limit — try another key immediately
_COOLDOWN_DAILY = 45 * 60.0   # daily free-tier style — park key ~45 min
_COOLDOWN_OTHER = 8.0         # other transient errors
_COOLDOWN_MAX_WAIT = 90.0     # wait out short rate windows before trying a key


def is_quota_or_rate(err: str) -> bool:
    e = err.lower()
    return (
        "429" in err
        or "resource_exhausted" in e
        or "quota" in e
        or "rate limit" in e
        or "ratelimit" in e
        or "too many requests" in e
    )


def is_daily_quota(err: str) -> bool:
    e = err.lower()
    return any(
        x in e
        for x in (
            "perday",
            "per day",
            "per_day",
            "daily",
            "free_tier_requests",
            "freetier",
            "free tier",
            "embed_content_free_tier",
            "generaterequestsperday",
            "embedcontentrequestsperday",
        )
    )


def _mask(key: str) -> str:
    if len(key) <= 10:
        return "***"
    return f"{key[:6]}…{key[-4:]}"


class GeminiKeyPool:
    """Round-robin + skip keys under cooldown; rotate on 429/quota."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rr = 0
        self._cooldown_until: dict[str, float] = {}
        self._fail_counts: dict[str, int] = {}
        self._clients: dict[str, Any] = {}

    def keys(self) -> list[str]:
        raw = list(config.gemini_api_keys or [])
        # preserve order, drop empties/dupes
        seen: set[str] = set()
        out: list[str] = []
        for k in raw:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def key_count(self) -> int:
        return len(self.keys())

    def _client(self, api_key: str) -> Any:
        from google import genai

        if api_key not in self._clients:
            self._clients[api_key] = genai.Client(api_key=api_key)
        return self._clients[api_key]

    def _available(self, keys: list[str], now: float) -> list[str]:
        return [k for k in keys if self._cooldown_until.get(k, 0.0) <= now]

    def acquire(self) -> tuple[str, Any]:
        """
        Return (api_key, genai.Client). Prefers keys not on cooldown.
        If all are cooling, waits briefly for the soonest, then uses it.
        """
        with self._lock:
            keys = self.keys()
            if not keys:
                raise RuntimeError(
                    "No Gemini API keys configured "
                    "(set GEMINI_API_KEY or GEMINI_API_KEYS)"
                )

            now = time.monotonic()
            ready = self._available(keys, now)

            if not ready:
                # Wait for the soonest-to-expire cooldown (capped)
                soonest = min(self._cooldown_until.get(k, now) for k in keys)
                wait = max(0.0, soonest - now)
                wait = min(wait, _COOLDOWN_MAX_WAIT)
                if wait > 0.05:
                    logger.warning(
                        "All %s Gemini keys cooling; waiting %.1fs then rotating",
                        len(keys),
                        wait,
                    )
                    # release lock while sleeping
                    pass
                else:
                    wait = 0.0
            else:
                wait = 0.0
                soonest = now

        if wait > 0:
            time.sleep(wait)

        with self._lock:
            keys = self.keys()
            now = time.monotonic()
            ready = self._available(keys, now) or keys

            # Round-robin among ready keys
            n = len(keys)
            for i in range(n):
                idx = (self._rr + i) % n
                k = keys[idx]
                if k in ready:
                    self._rr = (idx + 1) % n
                    logger.debug("Gemini key acquired %s", _mask(k))
                    return k, self._client(k)

            # fallback first key
            k = keys[0]
            self._rr = 1 % n
            return k, self._client(k)

    def mark_ok(self, api_key: str) -> None:
        with self._lock:
            self._fail_counts[api_key] = 0
            # clear short cooldowns on success
            until = self._cooldown_until.get(api_key, 0.0)
            if until and until - time.monotonic() < _COOLDOWN_RPM * 2:
                self._cooldown_until.pop(api_key, None)

    def mark_error(self, api_key: str, err: Exception | str) -> float:
        """
        Park this key for a while. Returns cooldown seconds applied.
        Daily free-tier → long park; plain 429 → short park + rotate.
        """
        msg = str(err)
        with self._lock:
            self._fail_counts[api_key] = self._fail_counts.get(api_key, 0) + 1
            fails = self._fail_counts[api_key]

            if is_daily_quota(msg):
                cool = _COOLDOWN_DAILY
                kind = "daily_quota"
            elif is_quota_or_rate(msg):
                cool = _COOLDOWN_RPM * min(3, fails)
                kind = "rate_limit"
            else:
                cool = _COOLDOWN_OTHER
                kind = "error"

            # Parse RetryInfo "retry in Xs" if present — the authoritative hint.
            # Gemini returns it for short-window limits (often ~30-60s) even when
            # the message text mentions free-tier/daily quotas. Honor it: never
            # park longer than ~3x the suggested retry.
            m = re.search(r"retry in\s+([\d.]+)\s*s", msg, re.I)
            if m:
                suggested = float(m.group(1)) + 5.0
                cool = min(cool, max(suggested, _COOLDOWN_OTHER + 5.0))
                kind = "retry_hint"

            until = time.monotonic() + cool
            prev = self._cooldown_until.get(api_key, 0.0)
            self._cooldown_until[api_key] = max(prev, until)

            logger.warning(
                "Gemini key %s marked %s (fail#%s) — cooldown %.0fs. "
                "Will rotate to other keys if available.",
                _mask(api_key),
                kind,
                fails,
                cool,
            )
            return cool

    def status(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            keys = self.keys()
            return {
                "total": len(keys),
                "ready": len(self._available(keys, now)),
                "keys": [
                    {
                        "mask": _mask(k),
                        "cooldown_s": max(0.0, self._cooldown_until.get(k, 0.0) - now),
                        "fails": self._fail_counts.get(k, 0),
                    }
                    for k in keys
                ],
            }


# Process-wide singleton
gemini_key_pool = GeminiKeyPool()
