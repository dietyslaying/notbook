import os
import yaml
import logging
import asyncio
import tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

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
        
        # 7. Save to Redis
        session_manager.save_user_session(user_id, cache_name)
        
        # 8. Generate Summary and Suggested Questions with background typing
        typing_task = asyncio.create_task(keep_typing(message.chat.id, bot))
        try:
            summary = gemini_service.generate_summary_and_suggestions(cache_name)
        finally:
            typing_task.cancel()
        
        await processing_msg.edit_text(summary)
        
    except Exception as e:
        logger.error(f"Document processing error for user {user_id}: {e}")
        await processing_msg.edit_text(prompts['messages']['error_processing'])
        
    finally:
        # 9. ALWAYS clean up the local file system
        if os.path.exists(local_path):
            os.remove(local_path)

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
        logger.error(f"Inference error for user {user_id}: {e}")
        await message.answer(prompts['messages']['error_inference'])
    finally:
        typing_task.cancel()

if __name__ == "__main__":
    logger.info("Starting Telegram Bot...")
    asyncio.run(dp.start_polling(bot))
