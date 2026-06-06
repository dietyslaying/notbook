import sqlite3
import yaml
import logging
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

DB_FILE = "sessions.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER PRIMARY KEY,
            cache_name TEXT,
            chat_history TEXT
        )
    """)
    conn.commit()
    conn.close()

# Initialize the database on startup
init_db()

def save_user_session(user_id: int, cache_name: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (user_id, cache_name, chat_history) 
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET cache_name=excluded.cache_name
    """, (user_id, cache_name, "[]"))
    conn.commit()
    conn.close()

def get_user_session(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT cache_name FROM sessions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return None

def clear_user_session(user_id: int) -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_chat_history(user_id: int) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_history FROM sessions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0])
    return []

def add_to_chat_history(user_id: int, role: str, text: str) -> None:
    history = get_chat_history(user_id)
    history.append({"role": role, "text": text})
    
    # Keep only the last 10 turns (20 messages)
    if len(history) > 20:
        history = history[-20:]
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions SET chat_history = ? WHERE user_id = ?
    """, (json.dumps(history), user_id))
    conn.commit()
    conn.close()
