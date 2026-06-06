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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS library (
            file_hash TEXT PRIMARY KEY,
            book_name TEXT,
            cache_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Initialize the database on startup
init_db()

def add_to_library(file_hash: str, book_name: str, cache_name: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO library (file_hash, book_name, cache_name) 
        VALUES (?, ?, ?)
        ON CONFLICT(file_hash) DO UPDATE SET book_name=excluded.book_name, cache_name=excluded.cache_name, timestamp=CURRENT_TIMESTAMP
    """, (file_hash, book_name, cache_name))
    conn.commit()
    conn.close()

def get_library_books():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_hash, book_name, cache_name FROM library ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"file_hash": r[0], "book_name": r[1], "cache_name": r[2]} for r in rows]

def get_book_by_hash(file_hash: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_hash, book_name, cache_name FROM library WHERE file_hash LIKE ?", (file_hash + "%",))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"file_hash": row[0], "book_name": row[1], "cache_name": row[2]}
    return None

def update_book_cache(file_hash: str, new_cache_name: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE library SET cache_name = ? WHERE file_hash = ?", (new_cache_name, file_hash))
    conn.commit()
    conn.close()

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
