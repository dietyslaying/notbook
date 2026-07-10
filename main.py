import sys
import os
sys.path.insert(0, os.path.abspath('notbook_ai'))

import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from config import config
from handlers.message_handler import MessageHandler
from handlers.callback_handler import CallbackHandler

logging.basicConfig(level=logging.INFO)

# Initialize systems
bot = Bot(token=config.telegram_token)
dp = Dispatcher()
msg_handler = MessageHandler()
cb_handler = CallbackHandler()

# --- RENDER FREE TIER HACK ---
async def handle_health(request):
    return web.Response(text="Bot is running!")
app = web.Application()
app.router.add_get('/', handle_health)

@dp.message(CommandStart())
async def start_cmd(message: Message):
    logging.info(f"Received /start from {message.from_user.id}")
    await message.answer(
        "<b>Notbook AI</b>\n\n"
        "I am your strictly book-smart medical study buddy. "
        "Ask me about diseases, drugs, or symptoms.",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_message(message: Message):
    logging.info(f"Received text message from {message.from_user.id}: {message.text}")
    try:
        await msg_handler.handle(message, bot)
        logging.info("Message successfully handled.")
    except Exception as e:
        logging.error(f"FATAL ERROR in message handler: {e}")

@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    await cb_handler.handle(callback)

async def main():
    # Start the dummy web server for Render
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Listening on port {port} for Render health checks...")

    # Delete any existing webhooks before polling
    await bot.delete_webhook(drop_pending_updates=True)

    # Start Telegram polling
    logging.info("Starting Notbook AI Telegram polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
