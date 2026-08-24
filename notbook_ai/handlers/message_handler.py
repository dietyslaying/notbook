"""Text pipeline: menus first, then RAG answers (optional book scope)."""

from __future__ import annotations

import hashlib
import html
import logging
import re
import uuid

from aiogram.types import Message

from config import config
from db.store import db
from handlers.menu import main_menu
from handlers.session_helpers import put_session
from handlers.telegram_ui import new_draft_id, send_screen, stream_draft
from intent_engine.engine import IntentEngine
from interfaces import ContentSession, IntentType
from presentation_engine.component_policy import ComponentPolicy
from renderer.telegram_renderer import TelegramRenderer
from services.library import book_label_for_user
from services.rate_limiter import RateLimiter
from services.safety import assess, compose_disclaimer
from workspaces.base import MedicalWorkspace
from workspaces.case import CaseWorkspace
from workspaces.comparison import ComparisonWorkspace
from workspaces.disease import DiseaseWorkspace
from workspaces.drug import DrugWorkspace
from workspaces.study import StudyWorkspace

logger = logging.getLogger(__name__)

_MODE_LABELS = {
    "brief": "Mode: 30-second",
    "standard": "Mode: Standard",
    "exam": "Mode: Exam",
    "ward": "Mode: Practical",
}


def _concept_id(user_id: int, query: str) -> str:
    raw = f"{user_id}:{query.strip().lower()}:{uuid.uuid4().hex[:8]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


class MessageHandler:
    def __init__(self) -> None:
        bot_cfg = config.raw_config.get("bot") or {}
        self.intent_engine = IntentEngine()
        self.disease_ws = DiseaseWorkspace()
        self.drug_ws = DrugWorkspace()
        self.comparison_ws = ComparisonWorkspace()
        self.study_ws = StudyWorkspace()
        self.case_ws = CaseWorkspace()
        self.fallback_ws = MedicalWorkspace()
        self.rate_limiter = RateLimiter(int(bot_cfg.get("rate_limit_per_minute", 8)))
        self.bot_cfg = bot_cfg

    async def handle(self, message: Message, bot) -> None:
        user = message.from_user
        user_id = user.id if user else 0
        text = (message.text or "").strip()
        if not text:
            await message.answer("Send a short medical study question in text.")
            return

        db.ensure_user(user_id)

        # Any slash command → main menu (no command soup)
        if text.startswith("/"):
            await send_screen(message, main_menu(user_id))
            return

        if not self.rate_limiter.allow(user_id):
            wait = self.rate_limiter.retry_after_seconds(user_id)
            await message.answer(f"Easy — rate limit hit. Try again in ~{wait}s.")
            return

        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass

        await self.answer_query(message, bot, user_id, text)

    async def answer_query(
        self, message: Message, bot, user_id: int, query: str
    ) -> None:
        """Public so callbacks can re-ask bookmark/recent queries."""
        safety = assess(query)
        study_mode = db.get_study_mode(user_id)
        preferred_ns = db.get_preferred_namespace(user_id)
        namespaces = [preferred_ns] if preferred_ns else None
        disclaimer = compose_disclaimer(
            safety,
            str(self.bot_cfg.get("disclaimer") or ""),
        )
        book_line = book_label_for_user(user_id)
        chat_id = message.chat.id
        is_private = getattr(message.chat, "type", "") == "private"
        draft_id = new_draft_id(user_id) if is_private else 0

        try:
            # Live draft bubble (private only) — final answer still sent via send_screen
            if draft_id:
                await stream_draft(bot, chat_id, draft_id, text="")
                await stream_draft(
                    bot,
                    chat_id,
                    draft_id,
                    markdown="# Working…\n\nReading your question and picking a study path.",
                )

            # Practical mode → always the full case framework.
            # Otherwise, patient vignettes (age/sex + complaint/duration) → case work-up.
            practical = study_mode == "ward"
            if practical or self.case_ws.matches(query):
                intent = None
                ndm = await self.case_ws.process(
                    query, study_mode=study_mode, namespaces=namespaces
                )
            else:
                intent = await self.intent_engine.classify(query)
                ws_kwargs = {"study_mode": study_mode, "namespaces": namespaces}
                if intent == IntentType.DISEASE:
                    ndm = await self.disease_ws.process(query, **ws_kwargs)
                elif intent == IntentType.DRUG:
                    ndm = await self.drug_ws.process(query, **ws_kwargs)
                elif intent == IntentType.COMPARISON:
                    ndm = await self.comparison_ws.process(query, **ws_kwargs)
                elif intent == IntentType.STUDY:
                    ndm = await self.study_ws.process(query, **ws_kwargs)
                else:
                    ndm = await self.fallback_ws.process(query, **ws_kwargs)
            intent_tag = "case" if intent is None else intent.value
            logger.info(
                "user=%s intent=%s mode=%s book=%s q=%r",
                user_id,
                intent_tag,
                study_mode,
                preferred_ns or "*",
                query[:80],
            )
            if draft_id:
                scope = book_line or "all sources"
                await stream_draft(
                    bot,
                    chat_id,
                    draft_id,
                    markdown=(
                        f"# Working…\n\n"
                        f"**Intent:** `{intent_tag}`  \n"
                        f"**Mode:** {study_mode}  \n"
                        f"**Sources:** {scope}\n\n"
                        f"Searching…"
                    ),
                )

            if draft_id and "error" not in ndm:
                title_preview = str(ndm.get("title") or "topic")[:80]
                await stream_draft(
                    bot,
                    chat_id,
                    draft_id,
                    markdown=(
                        f"# Almost ready\n\n"
                        f"Grounding answer for **{title_preview}**…\n\n"
                        f"Formatting rich study card."
                    ),
                )

            if "error" in ndm:
                err = ndm["error"]
                if safety.banner:
                    err = safety.banner + "\n\n" + err
                screen = TelegramRenderer.render_page(
                    {"kind": "error", "data": err},
                    concept_id="err",
                    page_index=0,
                    page_count=1,
                    has_details=False,
                )
                # Attach menu on errors
                screen.inline_keyboard = [
                    [{"text": "Books", "callback_data": "menu:books"}],
                    [{"text": "Menu", "callback_data": "menu:main"}],
                ]
                await send_screen(message, screen)
                return

            # Tag mode line with active book
            mode_label = _MODE_LABELS.get(study_mode, "")
            if book_line:
                mode_label = f"{mode_label} · {book_line}".strip(" ·")

            pages = ComponentPolicy.build_pages(
                ndm,
                disclaimer=disclaimer,
                emergency_banner=safety.banner,
                mode_label=mode_label,
            )
            concept_id = _concept_id(user_id, query)
            has_details = any(p.get("kind") == "section" for p in pages)
            pages_html = []
            for i, page in enumerate(pages):
                screen = TelegramRenderer.render_page(
                    page,
                    concept_id=concept_id,
                    page_index=i,
                    page_count=len(pages),
                    has_details=has_details,
                )
                pages_html.append(screen.html)

            session = ContentSession(
                concept_id=concept_id,
                user_id=user_id,
                query=query,
                intent=intent_tag,
                title=str(ndm.get("title") or "Topic"),
                pages_html=pages_html,
                source=str(ndm.get("source_citation") or ""),
                facts=list(ndm.get("core_facts") or []),
                raw_ndm=ndm,
                study_mode=study_mode,
                citations=list(ndm.get("citations") or []),
            )
            put_session(session)
            db.touch_recent(user_id, concept_id, session.title, query, intent_tag)

            first = TelegramRenderer.render_page(
                pages[0],
                concept_id=concept_id,
                page_index=0,
                page_count=len(pages),
                has_details=has_details,
                bookmarked=False,
            )
            # Final persist — draft is ephemeral until this lands
            await send_screen(message, first)

        except Exception:
            logger.exception("Message handling failed for user=%s", user_id)
            await message.answer(
                "Something went wrong on my side. Please try again in a moment."
            )

    async def handle_document(self, message: Message, bot) -> None:
        """Admin PDF ingest: caption 'ingest Book Name' OR just book name for admins."""
        user = message.from_user
        user_id = user.id if user else 0
        if user_id not in config.admin_user_ids:
            await message.answer(
                "PDF ingest is admin-only.\nUse Deploy Console → Library, or set ADMIN_USER_IDS."
            )
            return
        doc = message.document
        if not doc:
            return
        caption = (message.caption or "").strip()
        m = re.match(r"(?i)^(?:ingest\s+)?(.+)$", caption) if caption else None
        if not m:
            await message.answer(
                "Send a PDF with caption = <b>display name</b> for Telegram library.\n"
                "Example: <code>Murtagh General Practice</code>",
                parse_mode="HTML",
            )
            return
        book_name = m.group(1).strip()
        if book_name.lower().startswith("ingest "):
            book_name = book_name[7:].strip()
        if not (doc.file_name or "").lower().endswith(".pdf"):
            await message.answer("Send a PDF file.")
            return

        await message.answer(f"Ingesting <b>{_esc(book_name)}</b>…", parse_mode="HTML")
        tmp_dir = config.project_root / "data" / "ingest_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        dest = tmp_dir / f"{user_id}_{doc.file_unique_id}.pdf"
        try:
            import asyncio

            await bot.download(doc, destination=dest)
            from services.gemini_service import gemini_service
            from services.ingest import ingest_service

            result = await asyncio.to_thread(
                lambda: ingest_service.ingest_pdf(
                    str(dest), book_name, wipe_namespace=True
                )
            )
            gemini_service._ns_cache = None
            try:
                from handlers.internal_api import notify_console

                await notify_console(
                    "library_upload",
                    {
                        "book": result.get("book"),
                        "namespace": result.get("namespace"),
                        "chunks": result.get("chunks"),
                    },
                )
            except Exception:
                pass
            await message.answer(
                f"Done.\n"
                f"Display name: <b>{_esc(result['book'])}</b>\n"
                f"Namespace: <code>{_esc(result['namespace'])}</code>\n"
                f"Index: <code>{_esc(result.get('index') or '')}</code>\n"
                f"Pages: {result['pages']} · Chunks: {result['chunks']}\n\n"
                f"Users: Menu → Books to select it.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("Ingest failed")
            await message.answer(
                f"Ingest failed: {_esc(type(e).__name__)}: {_esc(str(e)[:300])}"
            )
        finally:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
