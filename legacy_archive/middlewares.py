import time
import yaml
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

RATE_LIMIT = config.get('bot', {}).get('rate_limit_per_minute', 5)

# In-memory token bucket for rate limiting
user_requests = defaultdict(list)

class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        now = time.time()
        
        # Clean up timestamps older than 60 seconds
        user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 60]
        
        if len(user_requests[user_id]) >= RATE_LIMIT:
            await event.answer(prompts['messages']['error_rate_limit'])
            return
            
        user_requests[user_id].append(now)
        return await handler(event, data)


import asyncio
import emoji

class ContentFilterMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        
        async def reject_and_warn(reason: str):
            try:
                await event.delete()
            except:
                pass
            
            warning = await event.answer(f"⚠️ {reason}")
            
            async def delete_warning(msg, delay):
                await asyncio.sleep(delay)
                try:
                    await msg.delete()
                except:
                    pass
            
            asyncio.create_task(delete_warning(warning, 5))

        # 1. Block via_bot (Inline bots & games)
        if event.via_bot:
            return await reject_and_warn("Inline bots and games are not allowed.")

        # 2. Block unwanted content types
        allowed_types = ["text", "document"]
        if event.content_type not in allowed_types:
            return await reject_and_warn(f"Sorry, {event.content_type}s are not allowed. Please send only text or study documents.")

        # 3. Check text for emojis and random commands
        if event.text:
            if emoji.emoji_count(event.text) > 0:
                return await reject_and_warn("Emojis are not allowed to maintain a clean study environment.")
                
            if event.text.startswith('/'):
                command = event.text.split()[0].lower()
                allowed_commands = ["/start", "/books", "/library", "/settings", "/help", "/mode", "/topics"]
                if command not in allowed_commands:
                    return await reject_and_warn("Unrecognized command.")

        # 4. Check documents for extension and size
        if event.document:
            file_name = event.document.file_name.lower() if event.document.file_name else ""
            allowed_exts = [".pdf", ".txt", ".epub", ".docx"]
            
            if not any(file_name.endswith(ext) for ext in allowed_exts):
                return await reject_and_warn("Only .pdf, .txt, .epub, and .docx files are supported.")
                
            file_size = event.document.file_size or 0
            if file_size > 15 * 1024 * 1024:
                return await reject_and_warn("File is too large! Please upload files under 15MB for optimal efficiency.")

        return await handler(event, data)
