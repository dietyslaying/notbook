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

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r", encoding="utf-8") as f:
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


async def send_paginated(message: Message, text: str) -> Message:
    """Format as HTML, split into ≤4000-char chunks, return the last sent Message object."""
    MAX_LEN = 4000
    formatted = format_for_telegram(text)

    if len(formatted) <= MAX_LEN:
        return await message.answer(formatted, parse_mode=ParseMode.HTML)

    paragraphs = formatted.split('\n\n')
    current = ""
    last_msg = None
    for para in paragraphs:
        addition = para + "\n\n"
        if len(current) + len(addition) > MAX_LEN:
            if current.strip():
                last_msg = await message.answer(current.strip(), parse_mode=ParseMode.HTML)
            current = addition
        else:
            current += addition
    if current.strip():
        last_msg = await message.answer(current.strip(), parse_mode=ParseMode.HTML)
    return last_msg


def continue_keyboard(namespace: str) -> InlineKeyboardMarkup:
    """Inline keyboard with a single Continue button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖  Continue reading…", callback_data=f"cont|{namespace}")]
    ])


THINKING_FRAMES = [
    "📖  Checking the archives…",
    "🔍  Cross-referencing the chapters…",
    "📚  Leafing through the pages…",
    "🗂️  Consulting the index…",
    "📝  Pulling the relevant sections…",
    "🔬  Examining the medical literature…",
    "📖  Almost there, just one more page…",
    "🗃️  Retrieving from the stacks…",
    "🧠  Synthesising the findings…",
    "✍️  Composing your answer…",
    "📖  Still with you, this one's thorough…",
]

async def animated_thinking(placeholder_msg, stop_event: asyncio.Event):
    """Cycles the placeholder through librarian phrases every 3s until stop_event fires."""
    idx = 0
    try:
        while not stop_event.is_set():
            await asyncio.sleep(3.2)
            if stop_event.is_set():
                break
            idx = (idx + 1) % len(THINKING_FRAMES)
            try:
                await placeholder_msg.edit_text(THINKING_FRAMES[idx])
            except Exception:
                pass  # placeholder may already be deleted
    except asyncio.CancelledError:
        pass

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

    keyboard.append([InlineKeyboardButton(text="📝 Study Modes", callback_data="open_modes")])
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


@dp.callback_query(F.data == "open_modes")
async def callback_open_modes(callback: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="💬 Normal Chat", callback_data="setmode|chat")],
        [InlineKeyboardButton(text="❓ Quiz Mode", callback_data="setmode|quiz")],
        [InlineKeyboardButton(text="🗂️ Flashcards Mode", callback_data="setmode|flashcards")],
        [InlineKeyboardButton(text="📝 Notes Mode", callback_data="setmode|notes")],
        [InlineKeyboardButton(text="⬅️ Back to Books", callback_data="page|0")]
    ]
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data.startswith("setmode|"))
async def callback_setmode(callback: CallbackQuery):
    mode = callback.data.split("|")[1]
    user_id = callback.from_user.id
    session_manager.set_user_mode(user_id, mode)
    
    msg = f"✅ Study Mode set to <b>{mode.title()}</b>!\nAsk me a question to begin."
    await callback.message.edit_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back to Books", callback_data="page|0")]]))
    await callback.answer()

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


@dp.callback_query(F.data.startswith("cont|"))
async def callback_continue(callback: CallbackQuery):
    """User pressed Continue — remove the button, show thinking placeholder, ask AI to carry on."""
    namespace = callback.data.split("|", 1)[1]
    user_id = callback.from_user.id

    # Remove the Continue button from the triggering message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()

    # Show animated thinking placeholder
    placeholder = await callback.message.answer(THINKING_FRAMES[0])
    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(callback.message.chat.id, bot))
    thinking_task = asyncio.create_task(animated_thinking(placeholder, stop_event))

    try:
        history = session_manager.get_chat_history(user_id)
        # Ask Gemini to continue exactly where it left off
        answer, is_complete = await asyncio.to_thread(
            gemini_service.query_rag,
            namespace,
            "Please continue your previous answer. Pick up exactly where you left off and finish your explanation.",
            history
        )

        session_manager.add_to_chat_history(user_id, "user", "[continued]")
        session_manager.add_to_chat_history(user_id, "model", answer)

        stop_event.set()
        thinking_task.cancel()
        try:
            await placeholder.delete()
        except Exception:
            pass

        last_msg = await send_paginated(callback.message, answer)
        if not is_complete and last_msg:
            try:
                await last_msg.edit_reply_markup(reply_markup=continue_keyboard(namespace))
            except Exception:
                pass

    except Exception as e:
        stop_event.set()
        thinking_task.cancel()
        try:
            await placeholder.delete()
        except Exception:
            pass
        logger.error(f"Continue error for user {user_id}: {e}")
        if "RATE_LIMIT_EXCEEDED" in str(e):
            await callback.message.answer("⏳ The AI is currently at maximum capacity. Please wait about 1 minute and try again.", parse_mode=ParseMode.HTML)
        else:
            await callback.message.answer(prompts['messages']['error_inference'], parse_mode=ParseMode.HTML)
    finally:
        typing_task.cancel()



@dp.message(F.text)
async def handle_question(message: Message):
    user_id = message.from_user.id

    namespace = session_manager.get_user_session(user_id)
    if not namespace:
        await message.answer(prompts['messages']['cache_expired'], parse_mode=ParseMode.HTML)
        return

    # 1. Fire off a placeholder immediately so the user sees action right away
    placeholder = await message.answer(THINKING_FRAMES[0])

    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(message.chat.id, bot))
    thinking_task = asyncio.create_task(animated_thinking(placeholder, stop_event))

    try:
        history = session_manager.get_chat_history(user_id)
        mode = session_manager.get_user_mode(user_id)
        
        stream_generator = gemini_service.query_rag_stream(namespace, message.text, history, mode)
        
        full_answer = ""
        is_complete_final = True
        last_edit_time = 0
        current_msg = placeholder
        
        async for chunk_text, chunk_complete in stream_generator:
            if not stop_event.is_set():
                stop_event.set()
                thinking_task.cancel()
                
            full_answer += chunk_text
            if chunk_complete is not None:
                is_complete_final = chunk_complete
                
            current_time = asyncio.get_event_loop().time()
            if current_time - last_edit_time > 1.5:
                formatted = format_for_telegram(full_answer)
                if len(formatted) < 4000:
                    try:
                        await current_msg.edit_text(formatted + " ✍️", parse_mode=ParseMode.HTML)
                        last_edit_time = current_time
                    except Exception:
                        pass
                        
        # Stream finished
        # 1. Truncate cleanly if cut off
        if not is_complete_final:
            match = re.search(r'(.+[.!?\n])', full_answer, flags=re.DOTALL)
            if match:
                full_answer = match.group(1).strip() + "..."
            else:
                full_answer = full_answer.rsplit(' ', 1)[0] + "..."

        session_manager.add_to_chat_history(user_id, "user", message.text)
        session_manager.add_to_chat_history(user_id, "model", full_answer)

        # 2. Delete the streaming placeholder if possible
        try:
            await current_msg.delete()
        except Exception:
            pass

        # 3. Send final formatted text
        last_msg = await send_paginated(message, full_answer)
        if not is_complete_final and last_msg:
            try:
                await last_msg.edit_reply_markup(
                    reply_markup=continue_keyboard(namespace)
                )
            except Exception:
                pass

    except Exception as e:
        stop_event.set()
        thinking_task.cancel()
        try:
            await placeholder.delete()
        except Exception:
            pass

        error_msg = str(e)
        logger.error(f"Inference error for user {user_id}: {error_msg}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            m = re.search(r'retry in ([\d\.]+)s', error_msg)
            wait = int(float(m.group(1))) + 1 if m else 30
            if wait > 60:
                await message.answer("⏳ The AI is currently too busy. Please try again in a minute.", parse_mode=ParseMode.HTML)
            else:
                await message.answer(
                    f"⏳ You're asking too fast! Please wait <b>{wait}s</b> and try again.",
                    parse_mode=ParseMode.HTML
                )
        else:
            if len(error_msg) > 2000:
                error_msg = error_msg[:2000] + "\n...[truncated]"
            await message.answer(prompts['messages']['error_inference'] + f"\n\n<pre>{html.escape(error_msg)}</pre>", parse_mode=ParseMode.HTML)
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
