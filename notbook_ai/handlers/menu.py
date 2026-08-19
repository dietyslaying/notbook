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
    modes = config.raw_config.get("study_modes") or {}
    mode_label = (modes.get(mode) or {}).get("label") or mode

    text = (
        f"<b>Notbook</b>\n\n"
        f"Source: <b>{_esc(book)}</b>\n"
        f"Mode: <b>{_esc(str(mode_label))}</b>\n"
        f"Cards due: <b>{due}</b>\n\n"
        f"Ask anything anytime, or use the menu."
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
        "<b>Sources</b>",
        "",
        "Pick a source as primary, or use All sources to search everything.",
        "",
    ]
    if not books:
        lines.append("<i>No sources uploaded yet.</i>")
        lines.append("Admin: upload via Deploy Console.")
    kb: list[list[dict]] = []
    # All books
    all_mark = "· " if selected else "✓ "
    kb.append(
        [{"text": f"{all_mark}All sources", "callback_data": "setbook:all"}]
    )
    for b in books[:24]:  # Telegram keyboard practical limit
        mark = "✓ " if b["namespace"] == selected else "· "
        label = (mark + b["display_name"])[:64]
        kb.append(
            [{"text": label, "callback_data": f"setbook:{b['token']}"}]
        )
        lines.append(f"• {_esc(b['display_name'])}")
    kb.append([{"text": "‹ Menu", "callback_data": "menu:main"}])
    return TelegramScreen(html="\n".join(lines), inline_keyboard=kb)


def mode_menu(user_id: int) -> TelegramScreen:
    cur = db.get_study_mode(user_id)
    modes = config.raw_config.get("study_modes") or {}
    lines = [
        "<b>Study mode</b>",
        "",
        "Pick how answers are shaped:",
        "",
    ]
    order = ["brief", "standard", "exam", "ward"]
    kb: list[list[dict]] = []
    row: list[dict] = []
    for key in order:
        meta = modes.get(key) or {}
        label = meta.get("label") or key
        focus = " ".join(str(meta.get("focus") or "").split())
        mark = "✓ " if key == cur else ""
        lines.append(f"• <b>{_esc(str(label))}</b>" + ("  ← current" if key == cur else ""))
        if focus:
            lines.append(f"  {_esc(focus)}")
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
    text = (
        f"<b>About Notbook</b>\n\n"
        f"A study companion that answers from your uploaded sources.\n\n"
        f"Upload your own PDFs in Deploy Console, ask questions, "
        f"quiz yourself, and review with flashcards."
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
