"""SQLite persistence: users, bookmarks, recent topics, flashcards (SRS), sessions."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from config import config


class Database:
    def __init__(self, path: Optional[Path] = None) -> None:
        data_dir = config.project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = path or (data_dir / "notbook.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    study_mode TEXT NOT NULL DEFAULT 'standard',
                    preferred_namespace TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    concept_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    query TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(user_id, concept_id)
                );

                CREATE TABLE IF NOT EXISTS recent_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    concept_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    query TEXT NOT NULL,
                    intent TEXT,
                    accessed_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recent_user
                    ON recent_topics(user_id, accessed_at DESC);

                CREATE TABLE IF NOT EXISTS content_sessions (
                    concept_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS flashcards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    concept_id TEXT,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    source TEXT,
                    ease REAL NOT NULL DEFAULT 2.5,
                    interval_days REAL NOT NULL DEFAULT 0,
                    repetitions INTEGER NOT NULL DEFAULT 0,
                    due_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cards_due
                    ON flashcards(user_id, due_at);

                CREATE TABLE IF NOT EXISTS quiz_state (
                    token TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )
            self._conn.commit()
            # Lightweight migrations for older DBs
            cols = {
                r[1]
                for r in self._conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "preferred_namespace" not in cols:
                self._conn.execute(
                    "ALTER TABLE users ADD COLUMN preferred_namespace TEXT NOT NULL DEFAULT ''"
                )
                self._conn.commit()

    def _now(self) -> float:
        return time.time()

    # --- users / study mode / book ---

    def ensure_user(self, user_id: int) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users (user_id, study_mode, preferred_namespace, created_at, updated_at)
                VALUES (?, 'standard', '', ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, now, now),
            )
            self._conn.commit()

    def get_study_mode(self, user_id: int) -> str:
        self.ensure_user(user_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT study_mode FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        mode = (row["study_mode"] if row else "standard") or "standard"
        return mode if mode in ("brief", "standard", "exam", "ward") else "standard"

    def set_study_mode(self, user_id: int, mode: str) -> None:
        if mode not in ("brief", "standard", "exam", "ward"):
            raise ValueError(f"Invalid study mode: {mode}")
        now = self._now()
        self.ensure_user(user_id)
        with self._lock:
            self._conn.execute(
                """
                UPDATE users SET study_mode = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (mode, now, user_id),
            )
            self._conn.commit()

    def get_preferred_namespace(self, user_id: int) -> str:
        self.ensure_user(user_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT preferred_namespace FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return (row["preferred_namespace"] if row else "") or ""

    def set_preferred_namespace(self, user_id: int, namespace: str) -> None:
        now = self._now()
        self.ensure_user(user_id)
        with self._lock:
            self._conn.execute(
                """
                UPDATE users SET preferred_namespace = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (namespace or "", now, user_id),
            )
            self._conn.commit()

    # --- bookmarks ---

    def add_bookmark(
        self, user_id: int, concept_id: str, title: str, query: str
    ) -> bool:
        now = self._now()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO bookmarks (user_id, concept_id, title, query, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, concept_id, title[:200], query[:500], now),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_bookmark(self, user_id: int, concept_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM bookmarks WHERE user_id = ? AND concept_id = ?",
                (user_id, concept_id),
            )
            self._conn.commit()

    def list_bookmarks(self, user_id: int, limit: int = 15) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT concept_id, title, query, created_at
                FROM bookmarks WHERE user_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def is_bookmarked(self, user_id: int, concept_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM bookmarks WHERE user_id = ? AND concept_id = ?",
                (user_id, concept_id),
            ).fetchone()
        return row is not None

    # --- recent topics ---

    def touch_recent(
        self,
        user_id: int,
        concept_id: str,
        title: str,
        query: str,
        intent: str = "",
    ) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                "DELETE FROM recent_topics WHERE user_id = ? AND concept_id = ?",
                (user_id, concept_id),
            )
            self._conn.execute(
                """
                INSERT INTO recent_topics
                    (user_id, concept_id, title, query, intent, accessed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, concept_id, title[:200], query[:500], intent, now),
            )
            # Keep last 40
            self._conn.execute(
                """
                DELETE FROM recent_topics WHERE id IN (
                    SELECT id FROM recent_topics
                    WHERE user_id = ?
                    ORDER BY accessed_at DESC
                    LIMIT -1 OFFSET 40
                )
                """,
                (user_id,),
            )
            self._conn.commit()

    def list_recent(self, user_id: int, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT concept_id, title, query, intent, accessed_at
                FROM recent_topics WHERE user_id = ?
                ORDER BY accessed_at DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- content sessions (durable pagination) ---

    def save_session(self, concept_id: str, user_id: int, payload: dict) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO content_sessions (concept_id, user_id, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(concept_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at,
                    user_id = excluded.user_id
                """,
                (concept_id, user_id, json.dumps(payload), now),
            )
            # Prune sessions older than 7 days
            self._conn.execute(
                "DELETE FROM content_sessions WHERE updated_at < ?",
                (now - 7 * 86400,),
            )
            self._conn.commit()

    def load_session(self, concept_id: str, user_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload, user_id, updated_at FROM content_sessions
                WHERE concept_id = ?
                """,
                (concept_id,),
            ).fetchone()
        if not row or row["user_id"] != user_id:
            return None
        if self._now() - row["updated_at"] > 7 * 86400:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    # --- flashcards / SRS ---

    def add_flashcard(
        self,
        user_id: int,
        front: str,
        back: str,
        *,
        concept_id: str = "",
        source: str = "",
        ease: float = 2.5,
    ) -> int:
        now = self._now()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO flashcards
                    (user_id, concept_id, front, back, source, ease,
                     interval_days, repetitions, due_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
                """,
                (
                    user_id,
                    concept_id,
                    front[:500],
                    back[:1500],
                    source[:300],
                    ease,
                    now,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def add_flashcards_bulk(
        self, user_id: int, cards: list[dict], concept_id: str = "", source: str = ""
    ) -> int:
        n = 0
        for c in cards:
            front = (c.get("front") or "").strip()
            back = (c.get("back") or "").strip()
            if front and back:
                self.add_flashcard(
                    user_id,
                    front,
                    back,
                    concept_id=concept_id,
                    source=source or c.get("source") or "",
                )
                n += 1
        return n

    def due_cards(self, user_id: int, limit: int = 20) -> list[dict]:
        now = self._now()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, front, back, source, ease, interval_days,
                       repetitions, due_at, concept_id
                FROM flashcards
                WHERE user_id = ? AND due_at <= ?
                ORDER BY due_at ASC LIMIT ?
                """,
                (user_id, now, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_due(self, user_id: int) -> int:
        now = self._now()
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM flashcards WHERE user_id = ? AND due_at <= ?",
                (user_id, now),
            ).fetchone()
        return int(row["c"] if row else 0)

    def count_cards(self, user_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM flashcards WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["c"] if row else 0)

    def get_card(self, card_id: int, user_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM flashcards WHERE id = ? AND user_id = ?",
                (card_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def update_card_srs(
        self,
        card_id: int,
        user_id: int,
        *,
        ease: float,
        interval_days: float,
        repetitions: int,
        due_at: float,
    ) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                UPDATE flashcards SET
                    ease = ?, interval_days = ?, repetitions = ?,
                    due_at = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (ease, interval_days, repetitions, due_at, now, card_id, user_id),
            )
            self._conn.commit()

    # --- quiz tokens ---

    def save_quiz(self, token: str, payload: dict, ttl: int = 3600) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO quiz_state (token, payload, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET
                    payload = excluded.payload,
                    expires_at = excluded.expires_at
                """,
                (token, json.dumps(payload), now + ttl),
            )
            self._conn.execute(
                "DELETE FROM quiz_state WHERE expires_at < ?", (now,)
            )
            self._conn.commit()

    def load_quiz(self, token: str) -> Optional[dict]:
        now = self._now()
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, expires_at FROM quiz_state WHERE token = ?",
                (token,),
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] < now:
                self._conn.execute("DELETE FROM quiz_state WHERE token = ?", (token,))
                self._conn.commit()
                return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    def delete_quiz(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM quiz_state WHERE token = ?", (token,))
            self._conn.commit()


db = Database()
