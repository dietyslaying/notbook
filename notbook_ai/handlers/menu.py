"""Inline-keyboard main menu (legacy Notbook vision: Books / Bookmarks / Settings)."""

from __future__ import annotations

import html
from typing import Optional

from config import config
from db.store import db
from interfaces import TelegramScreen
from services.library import book_label_for_user, list_books


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def main_menu(user_id: int) -> TelegramScreen:
    mode = db.get_study_mode(user_id)
    due = db.count_due(user_id)
    book = book_label_for_user(user_id)
    framing = " ".join(
        str((config.raw_config.get("bot") or {}).get("library_framing") or "").split()
    )
    modes = config.raw_config.get("study_modes") or {}
    mode_label = (modes.get(mode) or {}).get("label") or mode

    text = (
        f"<b>Notbook</b> — study library\n\n"
        f"Book: <b>{_esc(book)}</b>\n"
        f"Mode: <b>{_esc(str(mode_label))}</b>\n"
        f"Cards due: <b>{due}</b>\n\n"
        f"Type a question anytime, or use the menu.\n\n"
        f"<blockquote>{_esc(framing)}</blockquote>"
    )
    kb = [
        [
            {"text": "Books", "callback_data": "menu:books"},
            {"text": "Bookmarks", "callback_data": "menu:bookmarks"},
        ],
        [
            {"text": "Recent", "callback_data": "menu:recent"},
            {"text": f"Review ({due})", "callback_data": "menu:review"},
        ],
        [
            {"text": "Study mode", "callback_data": "menu:mode"},
            {"text": "About", "callback_data": "menu:about"},
        ],
    ]
    return TelegramScreen(html=text, inline_keyboard=kb)


def books_menu(user_id: int) -> TelegramScreen:
    selected = db.get_preferred_namespace(user_id)
    books = list_books()
    lines = [
        "<b>Library</b>",
        "",
        "Pick a textbook as primary source.",
        "Or use All books to search everything.",
        "",
    ]
    if not books:
        lines.append("<i>No books ingested yet.</i>")
        lines.append("Admin: upload via Deploy Console → Library.")
    kb: list[list[dict]] = []
    # All books
    all_mark = "· " if selected else "✓ "
    kb.append(
        [{"text": f"{all_mark}All books", "callback_data": "setbook:all"}]
    )
    for b in books[:24]:  # Telegram keyboard practical limit
        mark = "✓ " if b["namespace"] == selected else "· "
        label = (mark + b["display_name"])[:64]
        kb.append(
            [{"text": label, "callback_data": f"setbook:{b['token']}"}]
        )
        vec = b.get("vectors") or 0
        if vec:
            lines.append(f"• {_esc(b['display_name'])}  ({vec} chunks)")
        else:
            lines.append(f"• {_esc(b['display_name'])}")
    kb.append([{"text": "‹ Menu", "callback_data": "menu:main"}])
    return TelegramScreen(html="\n".join(lines), inline_keyboard=kb)


def mode_menu(user_id: int) -> TelegramScreen:
    cur = db.get_study_mode(user_id)
    modes = config.raw_config.get("study_modes") or {}
    lines = [
        "<b>Study mode</b>",
        "",
        "How packed answers should be:",
        "",
    ]
    order = ["brief", "standard", "exam", "ward"]
    kb: list[list[dict]] = []
    row: list[dict] = []
    for key in order:
        meta = modes.get(key) or {}
        label = meta.get("label") or key
        mark = "✓ " if key == cur else ""
        lines.append(f"• {_esc(str(label))}" + ("  ← current" if key == cur else ""))
        row.append({"text": f"{mark}{label}"[:32], "callback_data": f"setmode:{key}"})
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([{"text": "‹ Menu", "callback_data": "menu:main"}])
    return TelegramScreen(html="\n".join(lines), inline_keyboard=kb)


def bookmarks_menu(user_id: int) -> TelegramScreen:
    items = db.list_bookmarks(user_id, limit=12)
    lines = ["<b>Bookmarks</b>", ""]
    kb: list[list[dict]] = []
    if not items:
        lines.append("Nothing saved yet.")
        lines.append("On a topic, tap Save.")
    else:
        lines.append("Tap to re-ask a saved topic:")
        for i, b in enumerate(items):
            lines.append(f"{i + 1}. {_esc(b['title'])}")
            # reopen by re-running query via callback token stored briefly
            kb.append(
                [
                    {
                        "text": (b["title"] or "Topic")[:40],
                        "callback_data": f"reask:{i}",
                    }
                ]
            )
        # store queries in a simple side channel via bookmark order
    kb.append([{"text": "‹ Menu", "callback_data": "menu:main"}])
    return TelegramScreen(html="\n".join(lines), inline_keyboard=kb)


def recent_menu(user_id: int) -> TelegramScreen:
    items = db.list_recent(user_id, limit=10)
    lines = ["<b>Continue studying</b>", ""]
    kb: list[list[dict]] = []
    if not items:
        lines.append("No recent topics. Ask something first.")
    else:
        for i, r in enumerate(items):
            lines.append(f"{i + 1}. {_esc(r['title'])}")
            kb.append(
                [
                    {
                        "text": (r["title"] or "Topic")[:40],
                        "callback_data": f"reask_r:{i}",
                    }
                ]
            )
    kb.append([{"text": "‹ Menu", "callback_data": "menu:main"}])
    return TelegramScreen(html="\n".join(lines), inline_keyboard=kb)


def about_screen(user_id: int) -> TelegramScreen:
    framing = " ".join(
        str((config.raw_config.get("bot") or {}).get("library_framing") or "").split()
    )
    disc = " ".join(
        str((config.raw_config.get("bot") or {}).get("disclaimer") or "").split()
    )
    text = (
        f"<b>About Notbook</b>\n\n"
        f"{_esc(framing)}\n\n"
        f"{_esc(disc)}\n\n"
        f"Answers are compiled from your indexed textbooks only.\n"
        f"Not a clinician — a study library interface."
    )
    kb = [[{"text": "‹ Menu", "callback_data": "menu:main"}]]
    return TelegramScreen(html=text, inline_keyboard=kb)


def menu_for(screen_id: str, user_id: int) -> TelegramScreen:
    if screen_id == "books":
        return books_menu(user_id)
    if screen_id == "mode":
        return mode_menu(user_id)
    if screen_id == "bookmarks":
        return bookmarks_menu(user_id)
    if screen_id == "recent":
        return recent_menu(user_id)
    if screen_id == "about":
        return about_screen(user_id)
    return main_menu(user_id)
