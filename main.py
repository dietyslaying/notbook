"""Notbook AI — Telegram entrypoint (webhook + health port, polling fallback).

Webhook mode keeps the bot awake on Render's free tier: Telegram POSTs each
update to the service (inbound traffic), so Render never considers it idle.
Falls back to long polling automatically when no public URL is known
(local dev)."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PKG = _ROOT / "notbook_ai"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, Update

from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("notbook")

# Health + internal API first — so Render sees an open port even if handlers are slow.
app = web.Application()


async def handle_health(_request: web.Request) -> web.Response:
    return web.Response(text="Notbook AI is running")


# Telegram's official webhook source ranges (Bot API docs).
_TELEGRAM_NETS = [
    ipaddress.ip_network("149.154.160.0/20"),
    ipaddress.ip_network("91.108.4.0/22"),
]


def _from_telegram(request: web.Request) -> bool:
    """True if the request came from Telegram's datacenter ranges.

    Telegram only attaches the secret header to updates received AFTER the
    webhook was set with a secret; updates queued before that are delivered
    without it. Accepting those from Telegram's own IPs is safe (spoof-proof
    behind Render's proxy), while 403'ing everyone else.
    """
    candidates = [request.remote]
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if xff:
        candidates.append(xff)
    for ip in candidates:
        if not ip:
            continue
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if any(addr in net for net in _TELEGRAM_NETS):
            return True
    return False


async def handle_webhook(request: web.Request) -> web.Response:
    """Telegram POSTs updates here; verified with X-Telegram-Bot-Api-Secret-Token."""
    webhook_cfg = config.raw_config.get("webhook") or {}
    secret = os.getenv("WEBHOOK_SECRET_TOKEN") or webhook_cfg.get("secret_token") or ""
    given = request.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
    if secret and given != secret:
        if not _from_telegram(request):
            return web.Response(status=403, text="forbidden")
        logger.warning(
            "webhook delivery without secret header accepted from Telegram IP"
        )
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")
    try:
        update = Update.model_validate(payload)
        await dp.feed_webhook_update(bot, update, update_id=update.update_id)
    except Exception:
        logger.exception("webhook update failed")
        return web.Response(status=500, text="error")
    return web.Response(status=200, text="ok")


app.router.add_get("/", handle_health)
app.router.add_get("/health", handle_health)

# Webhook route registered BEFORE the router freezes (AppRunner.setup()).
webhook_cfg = config.raw_config.get("webhook") or {}
_webhook_path = str(webhook_cfg.get("path") or "/webhook")
if not _webhook_path.startswith("/"):
    _webhook_path = "/" + _webhook_path
app.router.add_post(_webhook_path, handle_webhook)
app.router.add_get(_webhook_path, handle_health)  # Telegram probe / browser visits

# Console ↔ bot authenticated routes (/internal/*)
from handlers.internal_api import register_internal_routes  # noqa: E402

register_internal_routes(app)

bot = Bot(token=config.telegram_token)
dp = Dispatcher()

# Lazy-ish handler init: import after logging setup; failures are logged not silent.
from handlers.callback_handler import CallbackHandler  # noqa: E402
from handlers.message_handler import MessageHandler  # noqa: E402

msg_handler = MessageHandler()
cb_handler = CallbackHandler()


@dp.message(CommandStart())
async def start_cmd(message: Message) -> None:
    from handlers.menu import main_menu
    from handlers.telegram_ui import send_screen
    from db.store import db

    uid = message.from_user.id if message.from_user else 0
    db.ensure_user(uid)
    await send_screen(message, main_menu(uid))


@dp.message(F.document)
async def handle_document(message: Message) -> None:
    try:
        await msg_handler.handle_document(message, bot)
    except Exception:
        logger.exception("Document handler error")
        await message.answer("Could not process that file.")


@dp.message(F.text)
async def handle_message(message: Message) -> None:
    try:
        await msg_handler.handle(message, bot)
    except Exception:
        logger.exception("Unhandled message error")
        try:
            await message.answer("Something went wrong. Please try again.")
        except Exception:
            pass


@dp.callback_query()
async def handle_callback(callback: CallbackQuery) -> None:
    await cb_handler.handle(callback)


async def main() -> None:
    # Bind health port ASAP for Render / Railway / Fly probes.
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health server on 0.0.0.0:%s", port)
    logger.info(
        "Admins: %s | model=%s | index=%s",
        list(config.admin_user_ids) or "(none)",
        config.raw_config["llm"]["model_name"],
        (config.raw_config.get("pinecone") or {}).get("index_name"),
    )

    # Ensure Pinecone index exists (create empty if missing) without blocking boot forever.
    try:
        from services.gemini_service import gemini_service

        await asyncio.to_thread(gemini_service._ensure_index)
        logger.info("Pinecone index ready")
    except Exception:
        logger.exception(
            "Pinecone index not ready yet — bot will still poll; "
            "RAG answers fail until index exists + books are ingested"
        )

    # Notify console that bot is up (best-effort)
    try:
        from handlers.internal_api import notify_console

        await notify_console(
            "bot_started",
            {
                "port": port,
                "external_url": os.getenv("RENDER_EXTERNAL_URL") or "",
            },
        )
    except Exception:
        pass

    webhook_cfg = config.raw_config.get("webhook") or {}
    public_url = (
        webhook_cfg.get("public_url")
        or os.getenv("RENDER_EXTERNAL_URL")
        or ""
    ).strip().rstrip("/")
    try:
        if public_url and webhook_cfg.get("enabled", True):
            path = str(webhook_cfg.get("path") or "/webhook")
            if not path.startswith("/"):
                path = "/" + path
            secret = (
                os.getenv("WEBHOOK_SECRET_TOKEN")
                or webhook_cfg.get("secret_token")
                or ""
            )
            await bot.set_webhook(
                f"{public_url}{path}",
                secret_token=secret or None,
                allowed_updates=["message", "callback_query"],
            )
            logger.info("Webhook set: %s%s", public_url, path)
            # Do NOT poll here: getUpdates conflicts with an active webhook
            # (Telegram 409). The aiohttp server keeps the process alive.
            await asyncio.Event().wait()
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Starting Notbook AI polling (no public URL → long polling)")
            await dp.start_polling(bot)
    finally:
        try:
            from handlers.internal_api import notify_console

            await notify_console("bot_stopping", {})
        except Exception:
            pass
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
