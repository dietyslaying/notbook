import os
import re
import yaml
import logging
import asyncio
import math
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
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

async def keep_typing(chat_id: int, bot: Bot):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(prompts['messages']['greeting'])

@dp.message(F.document)
async def handle_document(message: Message):
    await message.answer("Direct file uploads are disabled in this RAG bot. The admin adds books directly to the database. Use /books to see available books!")

def get_library_keyboard(page: int = 0):
    books = gemini_service.get_available_books()
    items_per_page = 8
    total_pages = math.ceil(len(books) / items_per_page) if books else 1
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_books = books[start_idx:end_idx]
    
    keyboard = []
    row = []
    for book in page_books:
        # We use the namespace directly as callback data
        btn = InlineKeyboardButton(text=book[:30], callback_data=f"book_{book[:30]}")
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="<< Prev", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Next >>", callback_data=f"page_{page+1}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("books", "library"))
async def cmd_books(message: Message):
    books = gemini_service.get_available_books()
    if not books:
        await message.answer("The library is currently empty. Ask the admin to run admin_ingest.py!")
        return
    
    await message.answer("Please select a book from the library:", reply_markup=get_library_keyboard(0))

@dp.callback_query(F.data.startswith("page_"))
async def callback_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[1])
    await callback.message.edit_reply_markup(reply_markup=get_library_keyboard(page))
    await callback.answer()

@dp.callback_query(F.data.startswith("book_"))
async def callback_book(callback: CallbackQuery):
    namespace = callback.data.split("_", 1)[1]
    
    user_id = callback.from_user.id
    # We save the namespace as the user's active session
    session_manager.save_user_session(user_id, namespace)
    
    msg = prompts['messages'].get('book_selected', "You've selected **{book_name}**. Ask me anything about it!").format(book_name=namespace)
    await callback.message.answer(msg)
    await callback.answer()

@dp.message(F.text)
async def handle_question(message: Message):
    user_id = message.from_user.id
    
    # 1. Verify active session (which is now the Pinecone namespace)
    namespace = session_manager.get_user_session(user_id)
    if not namespace:
        await message.answer(prompts['messages']['cache_expired'])
        return
        
    typing_task = asyncio.create_task(keep_typing(message.chat.id, bot))
    
    # 2. Query the LLM via RAG
    try:
        history = session_manager.get_chat_history(user_id)
        answer = gemini_service.query_rag(namespace, message.text, history)
        
        # 3. Save interaction
        session_manager.add_to_chat_history(user_id, "user", message.text)
        session_manager.add_to_chat_history(user_id, "model", answer)
        
        await message.answer(answer)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Inference error for user {user_id}: {error_msg}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            match = re.search(r'retry in ([\d\.]+)s', error_msg)
            if match:
                seconds = int(float(match.group(1))) + 1
                await message.answer(f"You are asking questions too quickly! Google's Free Tier limits us to 15 requests per minute. Please wait {seconds} seconds and try again.")
            else:
                await message.answer(prompts['messages']['error_rate_limit'])
        else:
            await message.answer(prompts['messages']['error_inference'])
    finally:
        typing_task.cancel()

# --- Webhook configuration ---
async def on_startup(bot: Bot) -> None:
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")

async def on_shutdown(bot: Bot) -> None:
    # Do not delete webhook on shutdown to avoid race condition during Render zero-downtime deploys
    logger.info("Shutdown initiated. Webhook left intact.")

if __name__ == "__main__":
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    
    if render_url:
        logger.info("Running in Webhook mode (Render)...")
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        app = web.Application()
        
        # Simple health check endpoint for Render
        async def health(request):
            return web.Response(text="OK", status=200)
        app.router.add_get("/", health)
        
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot
        ).register(app, path="/webhook")
        
        setup_application(app, dp, bot=bot)
        
        port = int(os.getenv("PORT", 8000))
        web.run_app(app, host="0.0.0.0", port=port)
    else:
        logger.info("Running in Polling mode (Local)...")
        asyncio.run(dp.start_polling(bot))
