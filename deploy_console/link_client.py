"""HTTP client: console → bot (and helpers for bot → console)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional


class LinkError(Exception):
    pass


def _token() -> str:
    return (
        os.getenv("INTERNAL_SERVICE_TOKEN")
        or os.getenv("CONSOLE_BOT_TOKEN")
        or ""
    ).strip()


def bot_base_url() -> str:
    return (
        os.getenv("BOT_BASE_URL")
        or os.getenv("NOTBOOK_BOT_URL")
        or ""
    ).rstrip("/")


def console_base_url() -> str:
    return (
        os.getenv("CONSOLE_BASE_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or ""
    ).rstrip("/")


def link_configured() -> bool:
    return bool(bot_base_url() and _token())


def bot_request(
    method: str,
    path: str,
    *,
    body: Any = None,
    timeout: int = 60,
) -> dict:
    base = bot_base_url()
    token = _token()
    if not base:
        raise LinkError("BOT_BASE_URL not set")
    if not token:
        raise LinkError("INTERNAL_SERVICE_TOKEN not set")
    url = base + path
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Notbook-Token": token,
        "Accept": "application/json",
        "User-Agent": "Notbook-Console-Link/1.0",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise LinkError(f"bot {method} {path} → {e.code}: {err[:400]}") from e
    except urllib.error.URLError as e:
        raise LinkError(f"bot unreachable: {e}") from e
