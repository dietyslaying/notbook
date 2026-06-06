import os
import re
import yaml
import logging
import asyncio
import tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart
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
    user_id = message.from_user.id
    doc = message.document
    mime_type = doc.mime_type
    
    # 1. Check File Size
    file_size_mb = doc.file_size / (1024 * 1024)
    if file_size_mb > config['cache']['max_file_size_mb'] and not local_api_url:
        await message.answer(prompts['messages']['error_file_too_large'])
        return

    # 2. Check File Type
    if mime_type not in config['cache']['allowed_mime_types']:
        await message.answer(prompts['messages']['error_unsupported_file'])
        return

    processing_msg = await message.answer(prompts['messages']['processing'])
    
    # 3. Create a safer tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        local_path = tmp.name
    
    try:
        # 4. Cleanup existing session if user is uploading a new document
        existing_cache = session_manager.get_user_session(user_id)
        if existing_cache:
            gemini_service.delete_document_cache(existing_cache)
        session_manager.clear_user_session(user_id)

        # 5. Download file locally
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, local_path)
        
        # 6. Create Cache via Gemini API
        cache_name = gemini_service.create_document_cache(local_path, mime_type)
        
        # 7. Save to DB
        session_manager.save_user_session(user_id, cache_name)
        
        # 8. Generate Summary and Suggested Questions with background typing
        typing_task = asyncio.create_task(keep_typing(message.chat.id, bot))
        try:
            summary = gemini_service.generate_summary_and_suggestions(cache_name)
        finally:
            typing_task.cancel()
        
        await processing_msg.edit_text(summary)
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Document processing error for user {user_id}: {error_msg}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            match = re.search(r'retry in ([\d\.]+)s', error_msg)
            if match:
                seconds = int(float(match.group(1))) + 1
                await processing_msg.edit_text(f"You are asking questions too quickly! Google's Free Tier limits us to 15 requests per minute. Please wait {seconds} seconds and try again.")
            else:
                await processing_msg.edit_text(prompts['messages']['error_rate_limit'])
        else:
            await processing_msg.edit_text(prompts['messages']['error_processing'])
        
    finally:
        # 9. ALWAYS clean up the local file system
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

@dp.message(F.text)
async def handle_question(message: Message):
    user_id = message.from_user.id
    
    # 1. Verify active session
    cache_name = session_manager.get_user_session(user_id)
    if not cache_name:
        await message.answer(prompts['messages']['cache_expired'])
        return
        
    typing_task = asyncio.create_task(keep_typing(message.chat.id, bot))
    
    # 2. Query the LLM
    try:
        history = session_manager.get_chat_history(user_id)
        answer = gemini_service.query_cached_document(cache_name, message.text, history)
        
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
