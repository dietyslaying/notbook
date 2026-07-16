"""Library / book catalog from Pinecone namespaces."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from services.gemini_service import gemini_service

logger = logging.getLogger(__name__)


def display_name_from_namespace(namespace: str) -> str:
    ns = (namespace or "").strip()
    if "|" in ns:
        return ns.split("|", 1)[1].strip() or ns
    return ns or "Untitled"


def namespace_token(namespace: str) -> str:
    """Short stable token for callback_data (≤12 hex)."""
    return hashlib.sha1((namespace or "").encode("utf-8")).hexdigest()[:12]


def list_books() -> list[dict[str, Any]]:
    """
    Return [{namespace, display_name, token, vectors?}, ...]
    Empty index → [].
    """
    try:
        index = gemini_service._ensure_index()
        stats = index.describe_index_stats()
        ns_map = stats.namespaces or {}
        books: list[dict[str, Any]] = []
        for ns, info in ns_map.items():
            if not ns or ns == "_user_sessions":
                continue
            count = 0
            if info is not None:
                count = int(getattr(info, "vector_count", None) or 0)
                if not count and isinstance(info, dict):
                    count = int(info.get("vector_count") or 0)
            books.append(
                {
                    "namespace": ns,
                    "display_name": display_name_from_namespace(ns),
                    "token": namespace_token(ns),
                    "vectors": count,
                }
            )
        books.sort(key=lambda b: b["display_name"].lower())
        return books
    except Exception as e:
        logger.warning("list_books failed: %s", e)
        return []


def resolve_namespace_token(token: str) -> str | None:
    if not token:
        return None
    if token == "all":
        return ""
    for b in list_books():
        if b["token"] == token:
            return b["namespace"]
    return None


def book_label_for_user(user_id: int) -> str:
    from db.store import db

    ns = db.get_preferred_namespace(user_id)
    if not ns:
        return "All books"
    return display_name_from_namespace(ns)
