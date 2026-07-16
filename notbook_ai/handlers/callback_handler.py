"""Callbacks: pagination, deep dive, quiz, bookmarks, cards, SRS review."""

from __future__ import annotations

import logging
import uuid

from aiogram.types import CallbackQuery

from config import config
from db.store import db
from handlers.session_helpers import get_session, put_session
from handlers.telegram_ui import edit_screen, send_screen
from presentation_engine.component_policy import ComponentPolicy
from renderer.telegram_renderer import TelegramRenderer
from services.gemini_service import gemini_service
from services.safety import assess, compose_disclaimer
from services.srs import sm2_review

logger = logging.getLogger(__name__)

_MODE_LABELS = {
    "brief": "Mode: 30-second",
    "standard": "Mode: Standard",
    "exam": "Mode: Exam",
    "ward": "Mode: Ward round",
}


class CallbackHandler:
    async def handle(self, callback: CallbackQuery) -> None:
        data = (callback.data or "").strip()
        user_id = callback.from_user.id if callback.from_user else 0

        if not data or data.startswith("noop:"):
            await callback.answer()
            return

        try:
            if data.startswith("pg:"):
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

    def _pages_for(self, session) -> list[dict]:
        safety = assess(session.query)
        bot_cfg = config.raw_config.get("bot") or {}
        disclaimer = compose_disclaimer(safety, str(bot_cfg.get("disclaimer") or ""))
        return ComponentPolicy.build_pages(
            session.raw_ndm,
            disclaimer=disclaimer,
            emergency_banner=safety.banner,
            mode_label=_MODE_LABELS.get(session.study_mode, ""),
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
            # Prefer citations page if present
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

    async def _show_citations(self, callback: CallbackQuery, data: str, user_id: int) -> None:
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
        # Refresh overview buttons
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
        await callback.answer("Building cards from library text…")
        ndm = session.raw_ndm or {}
        cards = await gemini_service.generate_flashcards(
            title=session.title,
            facts=session.facts,
            summary=str(ndm.get("summary") or ""),
            sections=list(ndm.get("detail_sections") or []),
        )
        if not cards:
            # deterministic fallback from facts
            cards = [{"front": f"{session.title}?", "back": f} for f in session.facts[:3]]
        n = db.add_flashcards_bulk(
            user_id,
            cards,
            concept_id=cid,
            source=session.source,
        )
        await callback.message.answer(
            f"Added <b>{n}</b> flashcards from this topic.\nUse /review to study due cards.",
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
        token = uuid.uuid4().hex[:10]
        db.save_quiz(
            token,
            {
                "correct_index": quiz["correct_index"],
                "explanation": quiz.get("explanation") or "",
                "concept_id": cid,
                "user_id": user_id,
            },
        )
        screen = TelegramRenderer.render_quiz(
            quiz["question"],
            quiz["options"],
            concept_id=cid,
            quiz_token=token,
        )
        await send_screen(callback.message, screen)

    async def _quiz_answer(self, callback: CallbackQuery, data: str, user_id: int) -> None:
        parts = data.split(":")
        if len(parts) != 4:
            await callback.answer("Bad quiz link", show_alert=True)
            return
        _, cid_short, token, idx_s = parts
        state = db.load_quiz(token)
        if not state or state.get("user_id") != user_id:
            await callback.answer("Quiz expired. Tap Quiz me again.", show_alert=True)
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
        # fcr:{id}:{quality}
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
        # Next due card
        nxt = db.due_cards(user_id, limit=1)
        due_n = db.count_due(user_id)
        if not nxt:
            try:
                await callback.message.edit_text(
                    "<b>Review complete</b>\n\n"
                    "No more cards due.\n"
                    f"Last card next interval: {result.interval_days:.1f} days.",
                    parse_mode="HTML",
                )
            except Exception:
                await callback.message.answer(
                    f"Review complete. Last interval: {result.interval_days:.1f} days."
                )
            await callback.answer("Saved")
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
