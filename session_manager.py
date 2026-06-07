import json
import logging
import os
import yaml
from pinecone import Pinecone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
pc = Pinecone(api_key=PINECONE_API_KEY)
index_name = config['pinecone']['index_name']
index = pc.Index(index_name)

NAMESPACE = "_user_sessions"

# In-memory fast cache so we don't hit Pinecone API on every single message
_session_cache = {}

def _get_vector_id(user_id: int) -> str:
    return f"user_{user_id}"

def _fetch_from_pinecone(user_id: int) -> dict:
    try:
        response = index.fetch(ids=[_get_vector_id(user_id)], namespace=NAMESPACE)
        if response and response.vectors:
            return response.vectors[_get_vector_id(user_id)].metadata
    except Exception as e:
        logger.error(f"Pinecone fetch error for user {user_id}: {e}")
    return {}

def _save_to_pinecone(user_id: int, metadata: dict):
    try:
        # Pinecone requires at least one non-zero value in a dense vector
        dummy_vector = [0.0] * 1024
        dummy_vector[0] = 1.0
        
        # Pinecone metadata values must be strings, numbers, booleans, or lists of strings
        # So we must serialize complex objects like chat history to a JSON string
        safe_metadata = {}
        for k, v in metadata.items():
            if isinstance(v, (dict, list)):
                safe_metadata[k] = json.dumps(v)
            else:
                safe_metadata[k] = v
                
        index.upsert(
            vectors=[{"id": _get_vector_id(user_id), "values": dummy_vector, "metadata": safe_metadata}],
            namespace=NAMESPACE
        )
    except Exception as e:
        logger.error(f"Pinecone upsert error for user {user_id}: {e}")

def save_user_session(user_id: int, book_name: str) -> None:
    # 1. Read existing metadata so we don't overwrite chat history
    metadata = _session_cache.get(user_id)
    if not metadata:
        metadata = _fetch_from_pinecone(user_id)
    
    # 2. Update book_name
    metadata["book_name"] = book_name
    _session_cache[user_id] = metadata
    
    # 3. Save
    _save_to_pinecone(user_id, metadata)

def get_user_session(user_id: int) -> str | None:
    metadata = _session_cache.get(user_id)
    if not metadata:
        metadata = _fetch_from_pinecone(user_id)
        _session_cache[user_id] = metadata
        
    return metadata.get("book_name")

def get_chat_history(user_id: int) -> list:
    metadata = _session_cache.get(user_id)
    if not metadata:
        metadata = _fetch_from_pinecone(user_id)
        _session_cache[user_id] = metadata
        
    history_raw = metadata.get("chat_history", "[]")
    if isinstance(history_raw, str):
        try:
            return json.loads(history_raw)
        except Exception:
            return []
    return history_raw

def add_to_chat_history(user_id: int, role: str, text: str) -> None:
    metadata = _session_cache.get(user_id)
    if not metadata:
        metadata = _fetch_from_pinecone(user_id)
        
    history = metadata.get("chat_history", "[]")
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
            
    history.append({"role": role, "text": text})
    
    # Keep only the last 10 turns (20 messages)
    if len(history) > 20:
        history = history[-20:]
        
    metadata["chat_history"] = history
    _session_cache[user_id] = metadata
    
    _save_to_pinecone(user_id, metadata)

# These old SQLite functions are no longer needed, 
# as the library is dynamically generated from Pinecone namespaces
def add_to_library(file_hash: str, book_name: str, cache_name: str):
    pass
def get_library_books():
    return []
def get_book_by_hash(file_hash: str):
    return None
def update_book_cache(file_hash: str, new_cache_name: str):
    pass
def clear_user_session(user_id: int):
    _session_cache.pop(user_id, None)
    try:
        index.delete(ids=[_get_vector_id(user_id)], namespace=NAMESPACE)
    except Exception:
        pass
