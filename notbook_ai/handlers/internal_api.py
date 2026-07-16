"""Authenticated HTTP API for console ↔ bot (Render-to-Render)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from aiohttp import web

from config import config
from services.internal_auth import internal_token, token_configured, verify_request_token

logger = logging.getLogger(__name__)

_STARTED = time.time()


def _unauthorized() -> web.Response:
    return web.json_response(
        {"ok": False, "error": "unauthorized — set INTERNAL_SERVICE_TOKEN on both services"},
        status=401,
    )


def _require_auth(request: web.Request) -> bool:
    if not token_configured():
        return False
    return verify_request_token(
        request.headers.get("Authorization"),
        request.headers.get("X-Notbook-Token"),
    )


async def handle_ping(request: web.Request) -> web.Response:
    if not _require_auth(request):
        return _unauthorized()
    return web.json_response(
        {
            "ok": True,
            "service": "notbook-bot",
            "ts": time.time(),
            "uptime_s": round(time.time() - _STARTED, 1),
        }
    )


async def handle_status(request: web.Request) -> web.Response:
    if not _require_auth(request):
        return _unauthorized()
    cfg = config.raw_config
    books_n = None
    index_ok = False
    try:
        from services.gemini_service import gemini_service
        from services.library import list_books

        books = list_books()
        books_n = len(books)
        index_ok = True
        try:
            gemini_service._ensure_index()
        except Exception:
            index_ok = False
    except Exception as e:
        logger.warning("status library: %s", e)

    return web.json_response(
        {
            "ok": True,
            "service": "notbook-bot",
            "uptime_s": round(time.time() - _STARTED, 1),
            "render": bool(os.getenv("RENDER")),
            "external_url": os.getenv("RENDER_EXTERNAL_URL") or "",
            "console_url": (os.getenv("CONSOLE_BASE_URL") or "").rstrip("/"),
            "secrets": {
                "telegram": bool(config.telegram_token),
                "gemini": bool(config.gemini_api_keys),
                "pinecone": bool(config.pinecone_api_key),
                "internal_token": token_configured(),
            },
            "llm_model": (cfg.get("llm") or {}).get("model_name"),
            "embeddings": cfg.get("embeddings") or {},
            "pinecone_index": (cfg.get("pinecone") or {}).get("index_name"),
            "reranker": (cfg.get("reranker") or {}).get("backend"),
            "index_ok": index_ok,
            "books_count": books_n,
            "admin_count": len(config.admin_user_ids),
        }
    )


async def handle_config(request: web.Request) -> web.Response:
    if not _require_auth(request):
        return _unauthorized()
    # No secrets — yaml only
    return web.json_response({"ok": True, "config": config.raw_config})


async def handle_books(request: web.Request) -> web.Response:
    if not _require_auth(request):
        return _unauthorized()
    from services.library import list_books

    books = list_books()
    return web.json_response({"ok": True, "books": books, "count": len(books)})


async def handle_cache_clear(request: web.Request) -> web.Response:
    if not _require_auth(request):
        return _unauthorized()
    from services.gemini_service import gemini_service

    gemini_service.cache.clear()
    gemini_service._ns_cache = None
    return web.json_response({"ok": True, "message": "cache + namespace list cleared"})


async def handle_library_refresh(request: web.Request) -> web.Response:
    if not _require_auth(request):
        return _unauthorized()
    from services.gemini_service import gemini_service

    gemini_service._ns_cache = None
    from services.library import list_books

    books = list_books()
    return web.json_response(
        {"ok": True, "message": "namespace cache refreshed", "books_count": len(books)}
    )


async def handle_console_event(request: web.Request) -> web.Response:
    """Console → bot webhook (e.g. after library upload)."""
    if not _require_auth(request):
        return _unauthorized()
    try:
        body = await request.json()
    except Exception:
        body = {}
    event = (body or {}).get("event") or "unknown"
    logger.info("console event: %s payload_keys=%s", event, list((body or {}).keys()))
    if event in ("library_upload", "library_refresh", "books_changed"):
        from services.gemini_service import gemini_service

        gemini_service._ns_cache = None
    return web.json_response({"ok": True, "received": event})


def register_internal_routes(app: web.Application) -> None:
    app.router.add_get("/internal/ping", handle_ping)
    app.router.add_get("/internal/status", handle_status)
    app.router.add_get("/internal/config", handle_config)
    app.router.add_get("/internal/library/books", handle_books)
    app.router.add_post("/internal/cache/clear", handle_cache_clear)
    app.router.add_post("/internal/library/refresh", handle_library_refresh)
    app.router.add_post("/internal/webhook/console", handle_console_event)


async def notify_console(event: str, payload: dict[str, Any] | None = None) -> bool:
    """Bot → console webhook (best-effort)."""
    base = (os.getenv("CONSOLE_BASE_URL") or "").rstrip("/")
    token = internal_token()
    if not base or not token:
        return False
    import aiohttp

    url = f"{base}/api/internal/webhook/bot"
    body = {"event": event, "service": "notbook-bot", "payload": payload or {}, "ts": time.time()}
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Notbook-Token": token,
                    "Content-Type": "application/json",
                },
            ) as resp:
                ok = 200 <= resp.status < 300
                if not ok:
                    logger.warning("console notify %s → %s", event, resp.status)
                return ok
    except Exception as e:
        logger.warning("console notify failed: %s", e)
        return False
