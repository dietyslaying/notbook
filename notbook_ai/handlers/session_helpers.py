"""Load/save content sessions (memory + SQLite)."""

from __future__ import annotations

from typing import Optional

from db.store import db
from interfaces import ContentSession
from services.session_store import session_store


def put_session(session: ContentSession) -> None:
    session_store.put(session)
    db.save_session(
        session.concept_id,
        session.user_id,
        session.model_dump(),
    )


def get_session(concept_id: str, user_id: int) -> Optional[ContentSession]:
    mem = session_store.get(concept_id)
    if mem and mem.user_id == user_id:
        return mem
    raw = db.load_session(concept_id, user_id)
    if not raw:
        return None
    try:
        sess = ContentSession(**raw)
        session_store.put(sess)
        return sess
    except Exception:
        return None
