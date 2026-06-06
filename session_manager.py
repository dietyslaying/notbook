import redis
import yaml
import logging
import json
import os
import logging
import json
import logging

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    else:
        redis_client = redis.Redis(
            host=config['redis']['host'],
            port=config['redis']['port'],
            db=config['redis']['db'],
            password=config['redis']['password'],
            decode_responses=True 
        )
    # Ping to check connection on startup
    redis_client.ping()
except redis.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {e}")
    raise SystemExit("Critical Error: Redis connection failed.")

def save_user_session(user_id: int, cache_name: str) -> None:
    key = f"user_session:{user_id}"
    ttl = config['cache']['redis_ttl']
    redis_client.set(key, cache_name, ex=ttl)

def get_user_session(user_id: int) -> str | None:
    key = f"user_session:{user_id}"
    return redis_client.get(key)

def clear_user_session(user_id: int) -> None:
    key = f"user_session:{user_id}"
    history_key = f"chat_history:{user_id}"
    redis_client.delete(key, history_key)

def get_chat_history(user_id: int) -> list:
    key = f"chat_history:{user_id}"
    history_json = redis_client.get(key)
    if history_json:
        return json.loads(history_json)
    return []

def add_to_chat_history(user_id: int, role: str, text: str) -> None:
    """role: 'user' or 'model'"""
    key = f"chat_history:{user_id}"
    history = get_chat_history(user_id)
    
    # Optional: we can just store pure dictionaries that match Gemini types.Content
    # since we pass them directly or manually parse them.
    history.append({"role": role, "text": text})
    
    # Keep only the last 10 turns (20 messages)
    if len(history) > 20:
        history = history[-20:]
        
    ttl = config['cache']['redis_ttl']
    redis_client.set(key, json.dumps(history), ex=ttl)
