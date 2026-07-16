"""Notbook AI — Telegram entrypoint (polling + health port)."""

from __future__ import annotations

import asyncio
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
from aiogram.types import CallbackQuery, Message

from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("notbook")

# Health app first — so Render sees an open port even if handlers are slow to import.
app = web.Application()


async def handle_health(_request: web.Request) -> web.Response:
    return web.Response(text="Notbook AI is running")


app.router.add_get("/", handle_health)
app.router.add_get("/health", handle_health)

bot = Bot(token=config.telegram_token)
dp = Dispatcher()

# Lazy-ish handler init: import after logging setup; failures are logged not silent.
from handlers.callback_handler import CallbackHandler  # noqa: E402
from handlers.message_handler import MessageHandler  # noqa: E402

msg_handler = MessageHandler()
cb_handler = CallbackHandler()


@dp.message(CommandStart())
async def start_cmd(message: Message) -> None:
    if message.text:
        await msg_handler.handle(message, bot)


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

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting Notbook AI polling")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
