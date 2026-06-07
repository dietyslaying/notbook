import os
import re
import yaml
import logging
import asyncio
import math
import html
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import gemini_service
import session_manager
from middlewares import RateLimitMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r") as f:
    prompts = yaml.safe_load(f)

local_api_url = config.get('bot', {}).get('telegram_local_api_url')
if local_api_url:
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(local_api_url)
    )
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"), session=session)
else:
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

dp = Dispatcher()
dp.message.middleware(RateLimitMiddleware())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_for_telegram(text: str) -> str:
    """Converts Gemini Markdown to Telegram-safe HTML.
    
    Order matters: escape HTML first, then convert markdown tokens.
    """
    # 1. Escape any raw HTML chars so they render as text, not tags
    text = html.escape(text)
    # 2. **bold** → <b>bold</b>  (non-greedy, single-line first)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # 3. Markdown headers (#, ##, ###) → <b>...</b>
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    # 4. Fenced code blocks
    text = re.sub(r'```(?:\w+)?\n(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    # 5. Inline code
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # 6. Stray lone asterisks used as bullets → bullet character
    text = re.sub(r'^\* ', '• ', text, flags=re.MULTILINE)
    return text


async def send_paginated(message: Message, text: str):
    """Format as HTML and split into ≤4096-char messages at paragraph boundaries."""
    MAX_LEN = 4000
    formatted = format_for_telegram(text)

    if len(formatted) <= MAX_LEN:
        await message.answer(formatted, parse_mode=ParseMode.HTML)
        return

    paragraphs = formatted.split('\n\n')
    current = ""
    for para in paragraphs:
        addition = para + "\n\n"
        if len(current) + len(addition) > MAX_LEN:
            if current.strip():
                await message.answer(current.strip(), parse_mode=ParseMode.HTML)
            current = addition
        else:
            current += addition
    if current.strip():
        await message.answer(current.strip(), parse_mode=ParseMode.HTML)


async def keep_typing(chat_id: int, bot: Bot):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Library keyboard  (defined before cmd_start so it can be called from it)
# ---------------------------------------------------------------------------

def get_library_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    books = gemini_service.get_available_books()
    items_per_page = 8
    total_pages = math.ceil(len(books) / items_per_page) if books else 1

    start_idx = page * items_per_page
    page_books = books[start_idx:start_idx + items_per_page]

    keyboard = []
    row = []
    for book in page_books:
        display = book[:28]
        btn = InlineKeyboardButton(text=f"📖 {display}", callback_data=f"book|{book}")
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"page|{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"page|{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: Message):
    greeting = prompts['messages']['greeting']
    books = gemini_service.get_available_books()
    if books:
        await message.answer(greeting, parse_mode=ParseMode.HTML,
                             reply_markup=get_library_keyboard(0))
    else:
        await message.answer(greeting, parse_mode=ParseMode.HTML)


@dp.message(Command("books", "library"))
async def cmd_books(message: Message):
    books = gemini_service.get_available_books()
    if not books:
        await message.answer("📭 The library is empty. Ask the admin to add books!")
        return
    await message.answer("📚 <b>Library</b>\nSelect a book to start your study session:",
                         parse_mode=ParseMode.HTML,
                         reply_markup=get_library_keyboard(0))


@dp.message(F.document)
async def handle_document(message: Message):
    await message.answer(
        "📁 Direct file uploads are disabled.\nUse /books to select a book from the library.",
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("page|"))
async def callback_page(callback: CallbackQuery):
    page = int(callback.data.split("|")[1])
    await callback.message.edit_reply_markup(reply_markup=get_library_keyboard(page))
    await callback.answer()


@dp.callback_query(F.data.startswith("book|"))
async def callback_book(callback: CallbackQuery):
    # Use pipe delimiter so book names with underscores/spaces are preserved in full
    namespace = callback.data.split("|", 1)[1]
    user_id = callback.from_user.id
    session_manager.save_user_session(user_id, namespace)

    msg = prompts['messages']['book_selected'].format(book_name=namespace)
    await callback.message.answer(msg, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.message(F.text)
async def handle_question(message: Message):
    user_id = message.from_user.id

    namespace = session_manager.get_user_session(user_id)
    if not namespace:
        await message.answer(prompts['messages']['cache_expired'], parse_mode=ParseMode.HTML)
        return

    typing_task = asyncio.create_task(keep_typing(message.chat.id, bot))

    try:
        history = session_manager.get_chat_history(user_id)
        answer = gemini_service.query_rag(namespace, message.text, history)

        session_manager.add_to_chat_history(user_id, "user", message.text)
        session_manager.add_to_chat_history(user_id, "model", answer)

        await send_paginated(message, answer)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Inference error for user {user_id}: {error_msg}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            m = re.search(r'retry in ([\d\.]+)s', error_msg)
            wait = int(float(m.group(1))) + 1 if m else 30
            await message.answer(
                f"⏳ You're asking too fast! Please wait <b>{wait}s</b> and try again.",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer(prompts['messages']['error_inference'], parse_mode=ParseMode.HTML)
    finally:
        typing_task.cancel()


# ---------------------------------------------------------------------------
# Webhook / Startup
# ---------------------------------------------------------------------------

async def on_startup(bot: Bot) -> None:
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutdown initiated. Webhook left intact.")


if __name__ == "__main__":
    render_url = os.getenv("RENDER_EXTERNAL_URL")

    if render_url:
        logger.info("Running in Webhook mode (Render)...")
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        app = web.Application()

        async def health(request):
            return web.Response(text="OK", status=200)
        app.router.add_get("/", health)

        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
        setup_application(app, dp, bot=bot)

        port = int(os.getenv("PORT", 8000))
        web.run_app(app, host="0.0.0.0", port=port)
    else:
        logger.info("Running in Polling mode (Local)...")
        asyncio.run(dp.start_polling(bot))
