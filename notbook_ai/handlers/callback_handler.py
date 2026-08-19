"""Callbacks: menus, book select, mode, pagination, quiz, cards, SRS."""

from __future__ import annotations

import logging
import uuid

from aiogram.types import CallbackQuery

from config import config
from db.store import db
from handlers.menu import menu_for
from handlers.session_helpers import get_session
from handlers.telegram_ui import edit_screen, send_screen
from presentation_engine.component_policy import ComponentPolicy
from renderer.telegram_renderer import TelegramRenderer
from services.gemini_service import gemini_service
from services.library import (
    book_label_for_user,
    display_name_from_namespace,
    resolve_namespace_token,
)
from services.safety import assess, compose_disclaimer
from services.srs import sm2_review

logger = logging.getLogger(__name__)

_MODE_LABELS = {
    "brief": "Mode: 30-second",
    "standard": "Mode: Standard",
    "exam": "Mode: Exam",
    "ward": "Mode: Practical",
}


class CallbackHandler:
    async def handle(self, callback: CallbackQuery) -> None:
        data = (callback.data or "").strip()
        user_id = callback.from_user.id if callback.from_user else 0

        if not data or data.startswith("noop:"):
            await callback.answer()
            return

        try:
            if data.startswith("menu:"):
                await self._menu(callback, data, user_id)
            elif data.startswith("setbook:"):
                await self._set_book(callback, data, user_id)
            elif data.startswith("setmode:"):
                await self._set_mode(callback, data, user_id)
            elif data.startswith("reask:"):
                await self._reask_bookmark(callback, data, user_id)
            elif data.startswith("reask_r:"):
                await self._reask_recent(callback, data, user_id)
            elif data.startswith("pg:"):
                await self._paginate(callback, data, user_id)
            elif data.startswith("deep:"):
                await self._deep_dive(callback, data, user_id)
            elif data.startswith("quiz:"):
                await self._quiz(callback, data, user_id)
            elif data.startswith("qa:"):
                await self._quiz_answer(callback, data, user_id)
            elif data.startswith("bm:"):
                await self._bookmark(callback, data, user_id)
            elif data.startswith("cards:"):
                await self._make_cards(callback, data, user_id)
            elif data.startswith("cite:"):
                await self._show_citations(callback, data, user_id)
            elif data.startswith("fcshow:"):
                await self._fc_show(callback, data, user_id)
            elif data.startswith("fcr:"):
                await self._fc_rate(callback, data, user_id)
            else:
                await callback.answer("Unknown action", show_alert=False)
        except Exception:
            logger.exception("Callback failed data=%r", data)
            await callback.answer("Action failed. Try again.", show_alert=True)

    async def _menu(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        screen_id = data.split(":", 1)[1] if ":" in data else "main"
        if screen_id == "review":
            await self._start_review(callback, user_id)
            return
        screen = menu_for(screen_id, user_id)
        await edit_screen(callback, screen)
        await callback.answer()

    async def _set_book(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        token = data.split(":", 1)[1]
        if token == "all":
            db.set_preferred_namespace(user_id, "")
            label = "All books"
        else:
            ns = resolve_namespace_token(token)
            if ns is None:
                await callback.answer("Book not found — reopen Books menu.", show_alert=True)
                return
            db.set_preferred_namespace(user_id, ns)
            label = display_name_from_namespace(ns)
        await callback.answer(f"Book: {label}")
        await edit_screen(callback, menu_for("books", user_id))

    async def _set_mode(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        mode = data.split(":", 1)[1]
        if mode not in ("brief", "standard", "exam", "ward"):
            await callback.answer("Bad mode", show_alert=True)
            return
        db.set_study_mode(user_id, mode)
        await callback.answer(f"Mode: {mode}")
        await edit_screen(callback, menu_for("mode", user_id))

    async def _reask_bookmark(
        self, callback: CallbackQuery, data: str, user_id: int
    ) -> None:
        idx = int(data.split(":")[1])
        items = db.list_bookmarks(user_id, limit=20)
        if idx < 0 or idx >= len(items):
            await callback.answer("Gone", show_alert=True)
            return
        await self._reopen_stored(
            callback, user_id, items[idx]["concept_id"], items[idx]["query"]
        )

    async def _reask_recent(
        self, callback: CallbackQuery, data: str, user_id: int
    ) -> None:
        idx = int(data.split(":")[1])
        items = db.list_recent(user_id, limit=15)
        if idx < 0 or idx >= len(items):
            await callback.answer("Gone", show_alert=True)
            return
        await self._reopen_stored(
            callback, user_id, items[idx]["concept_id"], items[idx]["query"]
        )

    async def _reopen_stored(
        self,
        callback: CallbackQuery,
        user_id: int,
        concept_id: str,
        fallback_query: str,
    ) -> None:
        """Re-render a stored session's first page — no regeneration.

        Recent/bookmark taps redirect to the previously generated result
        instead of paying for a fresh answer. If the session was pruned
        (>7 days), fall back to regenerating once.
        """
        session = get_session(concept_id, user_id)
        if not session:
            await callback.answer("Topic expired — re-asking…")
            from handlers.message_handler import MessageHandler

            mh = MessageHandler()
            await mh.answer_query(callback.message, callback.bot, user_id, fallback_query)
            return
        pages = self._pages_for(session)
        screen = TelegramRenderer.render_page(
            pages[0],
            concept_id=concept_id,
            page_index=0,
            page_count=len(pages),
            has_details=any(p.get("kind") == "section" for p in pages),
            bookmarked=db.is_bookmarked(user_id, concept_id),
        )
        await edit_screen(callback, screen)
        await callback.answer()

    async def _start_review(self, callback: CallbackQuery, user_id: int) -> None:
        cards = db.due_cards(user_id, limit=1)
        due_n = db.count_due(user_id)
        if not cards:
            await callback.answer("No cards due", show_alert=True)
            screen = menu_for("main", user_id)
            await edit_screen(callback, screen)
            return
        card = cards[0]
        screen = TelegramRenderer.render_flashcard(
            card["front"],
            card_id=int(card["id"]),
            remaining=due_n,
            revealed=False,
        )
        await edit_screen(callback, screen)
        await callback.answer("Review")

    def _pages_for(self, session):
        safety = assess(session.query)
        bot_cfg = config.raw_config.get("bot") or {}
        disclaimer = compose_disclaimer(safety, str(bot_cfg.get("disclaimer") or ""))
        book = book_label_for_user(session.user_id)
        mode_label = _MODE_LABELS.get(session.study_mode, "")
        if book:
            mode_label = f"{mode_label} · {book}".strip(" ·")
        return ComponentPolicy.build_pages(
            session.raw_ndm,
            disclaimer=disclaimer,
            emergency_banner=safety.banner,
            mode_label=mode_label,
        )

    async def _paginate(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        parts = data.split(":")
        if len(parts) != 3:
            await callback.answer("Bad page link", show_alert=True)
            return
        _, cid, page_s = parts
        try:
            page_i = int(page_s)
        except ValueError:
            await callback.answer("Bad page", show_alert=True)
            return
        session = get_session(cid, user_id)
        if not session:
            await callback.answer("Topic expired. Ask again.", show_alert=True)
            return
        pages = self._pages_for(session)
        page_i = max(0, min(page_i, len(pages) - 1))
        has_details = any(p.get("kind") == "section" for p in pages)
        screen = TelegramRenderer.render_page(
            pages[page_i],
            concept_id=cid,
            page_index=page_i,
            page_count=len(pages),
            has_details=has_details,
            bookmarked=db.is_bookmarked(user_id, cid),
        )
        await edit_screen(callback, screen)
        await callback.answer()

    async def _deep_dive(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        cid = data.split(":", 1)[1]
        session = get_session(cid, user_id)
        if not session:
            await callback.answer("Topic expired. Ask again.", show_alert=True)
            return
        pages = self._pages_for(session)
        target = 0
        for i, p in enumerate(pages):
            if p.get("kind") == "section":
                target = i
                break
        else:
            for i, p in enumerate(pages):
                if p.get("kind") == "citations":
                    target = i
                    break
            else:
                target = max(0, len(pages) - 1)
        has_details = any(p.get("kind") == "section" for p in pages)
        screen = TelegramRenderer.render_page(
            pages[target],
            concept_id=cid,
            page_index=target,
            page_count=len(pages),
            has_details=has_details,
            bookmarked=db.is_bookmarked(user_id, cid),
        )
        await edit_screen(callback, screen)
        await callback.answer("Deep dive")

    async def _show_citations(
        self, callback: CallbackQuery, data: str, user_id: int
    ) -> None:
        cid = data.split(":", 1)[1]
        session = get_session(cid, user_id)
        if not session:
            await callback.answer("Topic expired.", show_alert=True)
            return
        pages = self._pages_for(session)
        target = None
        for i, p in enumerate(pages):
            if p.get("kind") == "citations":
                target = i
                break
        if target is None:
            await callback.answer("No chunk citations for this topic.", show_alert=True)
            return
        has_details = any(p.get("kind") == "section" for p in pages)
        screen = TelegramRenderer.render_page(
            pages[target],
            concept_id=cid,
            page_index=target,
            page_count=len(pages),
            has_details=has_details,
            bookmarked=db.is_bookmarked(user_id, cid),
        )
        await edit_screen(callback, screen)
        await callback.answer("Sources")

    async def _bookmark(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        cid = data.split(":", 1)[1]
        session = get_session(cid, user_id)
        if not session:
            await callback.answer("Topic expired.", show_alert=True)
            return
        if db.is_bookmarked(user_id, cid):
            db.remove_bookmark(user_id, cid)
            await callback.answer("Bookmark removed")
        else:
            db.add_bookmark(user_id, cid, session.title, session.query)
            await callback.answer("Saved to bookmarks")
        pages = self._pages_for(session)
        screen = TelegramRenderer.render_page(
            pages[0],
            concept_id=cid,
            page_index=0,
            page_count=len(pages),
            has_details=any(p.get("kind") == "section" for p in pages),
            bookmarked=db.is_bookmarked(user_id, cid),
        )
        await edit_screen(callback, screen)

    async def _make_cards(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        cid = data.split(":", 1)[1]
        session = get_session(cid, user_id)
        if not session:
            await callback.answer("Topic expired.", show_alert=True)
            return
        await callback.answer("Building cards…")
        ndm = session.raw_ndm or {}
        cards = await gemini_service.generate_flashcards(
            title=session.title,
            facts=session.facts,
            summary=str(ndm.get("summary") or ""),
            sections=list(ndm.get("detail_sections") or []),
        )
        if not cards:
            cards = [{"front": f"{session.title}?", "back": f} for f in session.facts[:3]]
        n = db.add_flashcards_bulk(
            user_id, cards, concept_id=cid, source=session.source
        )
        await callback.message.answer(
            f"Added <b>{n}</b> flashcards.\nMenu → Review when due.",
            parse_mode="HTML",
        )

    async def _quiz(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        cid = data.split(":", 1)[1]
        session = get_session(cid, user_id)
        if not session:
            await callback.answer("Topic expired.", show_alert=True)
            return
        await callback.answer("Building quiz…")
        quiz = await gemini_service.generate_quiz_item(
            title=session.title,
            facts=session.facts,
            summary=str(session.raw_ndm.get("summary") or ""),
        )
        if "error" in quiz:
            await callback.message.answer(quiz["error"])
            return
        # Native Telegram quiz poll (Bot API sendPoll type="quiz")
        subject = (quiz.get("subject") or "General").strip() or "General"
        topic = (quiz.get("topic") or session.title).strip() or session.title
        difficulty = (quiz.get("difficulty") or "Medium").strip() or "Medium"
        stem = (quiz.get("question") or "").strip() or "Quiz"
        question = f"Subject: {subject} | Topic: {topic} | Difficulty: {difficulty}\n\n{stem}"
        options = [str(o).strip() for o in (quiz.get("options") or [])[:4] if str(o).strip()]
        if len(options) < 2:
            await callback.message.answer("Quiz came back incomplete. Try again.")
            return
        correct = int(quiz.get("correct_index", 0))
        correct = max(0, min(correct, len(options) - 1))
        explanation = (quiz.get("explanation") or "").strip()[:200]
        try:
            await callback.bot.send_poll(
                chat_id=callback.message.chat.id,
                question=question[:300],
                options=[o[:100] for o in options],
                type="quiz",
                correct_option_id=correct,
                explanation=explanation or None,
                is_anonymous=True,
            )
        except Exception:
            logger.exception("send_poll failed")
            await callback.message.answer("Couldn't send the quiz. Try again.")

    async def _quiz_answer(
        self, callback: CallbackQuery, data: str, user_id: int
    ) -> None:
        parts = data.split(":")
        if len(parts) != 4:
            await callback.answer("Bad quiz link", show_alert=True)
            return
        _, cid_short, token, idx_s = parts
        state = db.load_quiz(token)
        if not state or state.get("user_id") != user_id:
            await callback.answer("Quiz expired.", show_alert=True)
            return
        try:
            chosen = int(idx_s)
        except ValueError:
            await callback.answer("Bad choice", show_alert=True)
            return
        correct = chosen == int(state["correct_index"])
        screen = TelegramRenderer.render_quiz_result(
            correct=correct,
            explanation=str(state.get("explanation") or ""),
            concept_id=str(state.get("concept_id") or cid_short),
        )
        db.delete_quiz(token)
        await edit_screen(callback, screen)
        await callback.answer("Correct!" if correct else "Not quite")

    async def _fc_show(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        card_id = int(data.split(":")[1])
        card = db.get_card(card_id, user_id)
        if not card:
            await callback.answer("Card missing", show_alert=True)
            return
        due_n = db.count_due(user_id)
        screen = TelegramRenderer.render_flashcard(
            card["front"],
            card_id=card_id,
            remaining=due_n,
            revealed=True,
            back=card["back"],
        )
        await edit_screen(callback, screen)
        await callback.answer()

    async def _fc_rate(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        parts = data.split(":")
        if len(parts) != 3:
            await callback.answer("Bad rating", show_alert=True)
            return
        card_id = int(parts[1])
        quality = int(parts[2])
        card = db.get_card(card_id, user_id)
        if not card:
            await callback.answer("Card missing", show_alert=True)
            return
        result = sm2_review(
            quality=quality,
            ease=float(card["ease"]),
            interval_days=float(card["interval_days"]),
            repetitions=int(card["repetitions"]),
        )
        db.update_card_srs(
            card_id,
            user_id,
            ease=result.ease,
            interval_days=result.interval_days,
            repetitions=result.repetitions,
            due_at=result.due_at,
        )
        nxt = db.due_cards(user_id, limit=1)
        due_n = db.count_due(user_id)
        if not nxt:
            await edit_screen(callback, menu_for("main", user_id))
            await callback.answer("Review complete")
            return
        c = nxt[0]
        screen = TelegramRenderer.render_flashcard(
            c["front"],
            card_id=int(c["id"]),
            remaining=due_n,
            revealed=False,
        )
        await edit_screen(callback, screen)
        await callback.answer("Saved")
