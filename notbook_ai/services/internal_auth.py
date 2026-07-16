"""Shared service-to-service auth (bot ↔ console)."""

from __future__ import annotations

import hmac
import os
from typing import Optional


def internal_token() -> str:
    return (
        os.getenv("INTERNAL_SERVICE_TOKEN")
        or os.getenv("CONSOLE_BOT_TOKEN")
        or ""
    ).strip()


def token_configured() -> bool:
    return bool(internal_token())


def extract_bearer(header_value: Optional[str]) -> str:
    if not header_value:
        return ""
    h = header_value.strip()
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return h


def verify_request_token(
    authorization: Optional[str] = None,
    x_token: Optional[str] = None,
) -> bool:
    expected = internal_token()
    if not expected:
        return False
    got = extract_bearer(authorization) or (x_token or "").strip()
    if not got:
        return False
    return hmac.compare_digest(got, expected)
