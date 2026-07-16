"""Text pipeline: commands, safety, rate limit, intent, RAG, pagination."""

from __future__ import annotations

import hashlib
import html
import logging
import re
import uuid
from pathlib import Path

from aiogram.types import Message

from config import config
from db.store import db
from handlers.session_helpers import put_session
from handlers.telegram_ui import send_screen
from intent_engine.engine import IntentEngine
from interfaces import ContentSession, IntentType
from presentation_engine.component_policy import ComponentPolicy
from renderer.telegram_renderer import TelegramRenderer
from services.gemini_service import gemini_service
from services.rate_limiter import RateLimiter
from services.safety import assess, compose_disclaimer
from workspaces.base import MedicalWorkspace
from workspaces.comparison import ComparisonWorkspace
from workspaces.disease import DiseaseWorkspace
from workspaces.drug import DrugWorkspace
from workspaces.study import StudyWorkspace

logger = logging.getLogger(__name__)

_MODE_LABELS = {
    "brief": "Mode: 30-second",
    "standard": "Mode: Standard",
    "exam": "Mode: Exam",
    "ward": "Mode: Ward round",
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

        # Slash commands
        if text.startswith("/"):
            await self._command(message, bot, user_id, text)
            return

        if not self.rate_limiter.allow(user_id):
            wait = self.rate_limiter.retry_after_seconds(user_id)
            await message.answer(f"Easy — rate limit hit. Try again in ~{wait}s.")
            return

        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass

        await self._answer_query(message, bot, user_id, text)

    async def _command(self, message: Message, bot, user_id: int, text: str) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/start", "/help"):
            due = db.count_due(user_id)
            mode = db.get_study_mode(user_id)
            await message.answer(
                "<b>Notbook AI</b> — compiled textbook study library\n\n"
                "Not a doctor. Answers come <b>only</b> from books in this bot's database.\n\n"
                "<b>Ask</b> any study question in plain text.\n\n"
                "<b>Commands</b>\n"
                "/mode — study mode (30s / standard / exam / ward)\n"
                "/bookmarks — saved topics\n"
                "/recent — continue studying\n"
                f"/review — flashcards due ({due})\n"
                "/cards — card count\n"
                "/help — this message\n\n"
                f"Current mode: <b>{_esc(mode)}</b>\n\n"
                f"<blockquote>{_esc(self.bot_cfg.get('library_framing') or '')}</blockquote>",
                parse_mode="HTML",
            )
            return

        if cmd == "/mode":
            await self._cmd_mode(message, user_id, arg)
            return
        if cmd == "/bookmarks":
            await self._cmd_bookmarks(message, user_id)
            return
        if cmd == "/recent":
            await self._cmd_recent(message, user_id)
            return
        if cmd in ("/review", "/cards"):
            await self._cmd_review(message, user_id, list_only=(cmd == "/cards"))
            return
        if cmd == "/ingest":
            await message.answer(
                "Admin: send a PDF as a document with caption:\n"
                "<code>ingest Book Name Here</code>\n"
                "Your Telegram user id must be in ADMIN_USER_IDS.",
                parse_mode="HTML",
            )
            return

        await message.answer("Unknown command. Try /help")

    async def _cmd_mode(self, message: Message, user_id: int, arg: str) -> None:
        modes = config.raw_config.get("study_modes") or {}
        if not arg:
            cur = db.get_study_mode(user_id)
            lines = ["<b>Study modes</b>", f"Current: <b>{_esc(cur)}</b>", ""]
            for key, meta in modes.items():
                label = (meta or {}).get("label") or key
                lines.append(f"• <code>/mode {key}</code> — {_esc(label)}")
            lines.append("")
            lines.append("Modes change how tightly the library answer is packed.")
            await message.answer("\n".join(lines), parse_mode="HTML")
            return
        key = arg.strip().lower()
        if key not in ("brief", "standard", "exam", "ward"):
            await message.answer("Use: brief | standard | exam | ward")
            return
        db.set_study_mode(user_id, key)
        label = (modes.get(key) or {}).get("label") or key
        await message.answer(f"Mode set to <b>{_esc(label)}</b>.", parse_mode="HTML")

    async def _cmd_bookmarks(self, message: Message, user_id: int) -> None:
        items = db.list_bookmarks(user_id)
        if not items:
            await message.answer("No bookmarks yet. Open a topic and tap Save.")
            return
        lines = ["<b>Bookmarks</b>", ""]
        for i, b in enumerate(items, 1):
            lines.append(f"{i}. <b>{_esc(b['title'])}</b>")
            lines.append(f"   <code>{_esc(b['query'][:80])}</code>")
        lines.append("")
        lines.append("Re-ask the query text, or use /recent for latest topics.")
        await message.answer("\n".join(lines), parse_mode="HTML")

    async def _cmd_recent(self, message: Message, user_id: int) -> None:
        items = db.list_recent(user_id)
        if not items:
            await message.answer("No recent topics yet. Ask something to start.")
            return
        lines = ["<b>Continue studying</b>", ""]
        for i, r in enumerate(items, 1):
            lines.append(f"{i}. <b>{_esc(r['title'])}</b>")
            lines.append(f"   {_esc(r['query'][:100])}")
        lines.append("")
        lines.append("Copy a query line and send it again to reopen.")
        await message.answer("\n".join(lines), parse_mode="HTML")

    async def _cmd_review(self, message: Message, user_id: int, list_only: bool = False) -> None:
        total = db.count_cards(user_id)
        due_n = db.count_due(user_id)
        if list_only:
            await message.answer(
                f"You have <b>{total}</b> cards · <b>{due_n}</b> due.\n"
                "Use /review to study.",
                parse_mode="HTML",
            )
            return
        cards = db.due_cards(user_id, limit=1)
        if not cards:
            await message.answer(
                f"No cards due. Library total: {total}.\n"
                "Open a topic → Cards to generate flashcards from the books."
            )
            return
        card = cards[0]
        screen = TelegramRenderer.render_flashcard(
            card["front"],
            card_id=int(card["id"]),
            remaining=due_n,
            revealed=False,
        )
        await send_screen(message, screen)

    async def _answer_query(self, message: Message, bot, user_id: int, query: str) -> None:
        safety = assess(query)
        study_mode = db.get_study_mode(user_id)
        disclaimer = compose_disclaimer(
            safety,
            str(self.bot_cfg.get("disclaimer") or ""),
        )

        try:
            intent = await self.intent_engine.classify(query)
            logger.info("user=%s intent=%s mode=%s q=%r", user_id, intent.value, study_mode, query[:80])

            if intent == IntentType.DISEASE:
                ndm = await self.disease_ws.process(query, study_mode=study_mode)
            elif intent == IntentType.DRUG:
                ndm = await self.drug_ws.process(query, study_mode=study_mode)
            elif intent == IntentType.COMPARISON:
                ndm = await self.comparison_ws.process(query, study_mode=study_mode)
            elif intent == IntentType.STUDY:
                ndm = await self.study_ws.process(query, study_mode=study_mode)
            else:
                ndm = await self.fallback_ws.process(query, study_mode=study_mode)

            if "error" in ndm:
                # Even on miss: show safety banner if needed
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
                await send_screen(message, screen)
                return

            pages = ComponentPolicy.build_pages(
                ndm,
                disclaimer=disclaimer,
                emergency_banner=safety.banner,
                mode_label=_MODE_LABELS.get(study_mode, ""),
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
                intent=intent.value,
                title=str(ndm.get("title") or "Topic"),
                pages_html=pages_html,
                source=str(ndm.get("source_citation") or ""),
                facts=list(ndm.get("core_facts") or []),
                raw_ndm=ndm,
                study_mode=study_mode,
                citations=list(ndm.get("citations") or []),
            )
            put_session(session)
            db.touch_recent(user_id, concept_id, session.title, query, intent.value)

            first = TelegramRenderer.render_page(
                pages[0],
                concept_id=concept_id,
                page_index=0,
                page_count=len(pages),
                has_details=has_details,
                bookmarked=False,
            )
            await send_screen(message, first)

        except Exception:
            logger.exception("Message handling failed for user=%s", user_id)
            await message.answer("Something went wrong on my side. Please try again in a moment.")

    async def handle_document(self, message: Message, bot) -> None:
        """Admin PDF ingest via document + caption 'ingest Book Name'."""
        user = message.from_user
        user_id = user.id if user else 0
        if user_id not in config.admin_user_ids:
            await message.answer("Ingest is admin-only. Set ADMIN_USER_IDS.")
            return
        doc = message.document
        if not doc:
            return
        caption = (message.caption or "").strip()
        m = re.match(r"(?i)^ingest\s+(.+)$", caption)
        if not m:
            await message.answer(
                "Caption must be: <code>ingest Book Name</code>", parse_mode="HTML"
            )
            return
        book_name = m.group(1).strip()
        if not (doc.file_name or "").lower().endswith(".pdf"):
            await message.answer("Send a PDF file.")
            return

        await message.answer(f"Ingesting <b>{_esc(book_name)}</b>…", parse_mode="HTML")
        tmp_dir = config.project_root / "data" / "ingest_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        dest = tmp_dir / f"{user_id}_{doc.file_unique_id}.pdf"
        try:
            await bot.download(doc, destination=dest)
            from services.ingest import ingest_service

            updates: list[str] = []

            def progress(msg: str) -> None:
                updates.append(msg)

            result = await bot.loop.run_in_executor(
                None,
                lambda: ingest_service.ingest_pdf(
                    str(dest), book_name, progress=progress, wipe_namespace=True
                ),
            )
            await message.answer(
                f"Done.\n"
                f"Book: <b>{_esc(result['book'])}</b>\n"
                f"Namespace: <code>{_esc(result['namespace'])}</code>\n"
                f"Pages: {result['pages']} · Chunks: {result['chunks']}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("Ingest failed")
            await message.answer(f"Ingest failed: {_esc(type(e).__name__)}: {_esc(str(e)[:300])}")
        finally:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
