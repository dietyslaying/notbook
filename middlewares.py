import time
import yaml
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r") as f:
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
