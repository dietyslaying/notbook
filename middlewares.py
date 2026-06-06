import yaml
from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable
import session_manager

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r") as f:
    prompts = yaml.safe_load(f)

RATE_LIMIT = config.get('bot', {}).get('rate_limit_per_minute', 5)

class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        key = f"rate_limit:{user_id}"
        
        current = session_manager.redis_client.get(key)
        
        if current and int(current) >= RATE_LIMIT:
            await event.answer(prompts['messages']['error_rate_limit'])
            return
            
        pipe = session_manager.redis_client.pipeline()
        pipe.incr(key)
        if not current:
            pipe.expire(key, 60)
        pipe.execute()

        return await handler(event, data)
