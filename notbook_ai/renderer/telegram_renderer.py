"""ADHD-first Telegram HTML renderer with pagination + library actions."""

from __future__ import annotations

import html
import re

from interfaces import TelegramScreen


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _body_lines(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    out: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            out.append("")
            continue
        if line.startswith("- "):
            out.append(f"• {_esc(line[2:].strip())}")
        else:
            out.append(_esc(line))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


class TelegramRenderer:
    @staticmethod
    def render_page(
        page: dict,
        *,
        concept_id: str,
        page_index: int,
        page_count: int,
        has_details: bool,
        bookmarked: bool = False,
    ) -> TelegramScreen:
        kind = page.get("kind", "overview")

        if kind == "error":
            body = f"<b>Couldn’t answer</b>\n\n{_esc(page.get('data') or 'Unknown error')}"
            return TelegramScreen(html=body, inline_keyboard=[], page_index=0, page_count=1)

        parts: list[str] = []

        if kind == "overview":
            title = page.get("title") or "Topic"
            mode = (page.get("mode_label") or "").strip()
            head = f"<b>{_esc(title)}</b>"
            if mode:
                head += f"\n{_esc(mode)}"
            parts.append(head)
            banner = (page.get("emergency_banner") or "").strip()
            if banner:
                parts.append("")
                parts.append(f"<blockquote>{_esc(banner)}</blockquote>")
            summary = (page.get("summary") or "").strip()
            if summary:
                parts.append("")
                parts.append(_esc(summary))
            facts = page.get("facts") or []
            if facts:
                parts.append("")
                for fact in facts[:3]:
                    parts.append(f"• {_esc(fact)}")
            disc = (page.get("disclaimer") or "").strip()
            if disc:
                parts.append("")
                parts.append(f"<blockquote>{_esc(disc)}</blockquote>")

        elif kind == "section":
            parts.append(f"<b>{_esc(page.get('heading') or 'Details')}</b>")
            parts.append("")
            parts.append(_body_lines(page.get("body") or ""))

        elif kind == "citations":
            parts.append("<b>Sources in this library</b>")
            parts.append("")
            for c in (page.get("citations") or [])[:6]:
                ref = c.get("ref") or "?"
                book = c.get("book") or "Textbook"
                page_n = c.get("page", "N/A")
                chunk = c.get("chunk_id") or ""
                score = c.get("hybrid_score") or c.get("score") or 0
                parts.append(
                    f"<b>[{_esc(ref)}]</b> {_esc(book)}, p.{_esc(page_n)}"
                    f" · id {_esc(str(chunk)[:40])}"
                    f" · score {_esc(f'{float(score):.3f}')}"
                )
                excerpt = (c.get("excerpt") or "").strip()
                if excerpt:
                    parts.append(f"<blockquote>{_esc(excerpt[:220])}</blockquote>")
                parts.append("")

        elif kind == "source":
            parts.append("<b>Primary citation</b>")
            parts.append("")
            parts.append(f"<blockquote>{_esc(page.get('source') or 'Textbook')}</blockquote>")
            disc = (page.get("disclaimer") or "").strip()
            if disc:
                parts.append("")
                parts.append(_esc(disc))
        else:
            parts.append(_esc(str(page)))

        html_msg = "\n".join(parts).strip()
        keyboard = TelegramRenderer._keyboard(
            concept_id=concept_id,
            page_index=page_index,
            page_count=page_count,
            has_details=has_details,
            kind=kind,
            bookmarked=bookmarked,
        )
        return TelegramScreen(
            html=html_msg,
            inline_keyboard=keyboard,
            page_index=page_index,
            page_count=page_count,
        )

    @staticmethod
    def _keyboard(
        *,
        concept_id: str,
        page_index: int,
        page_count: int,
        has_details: bool,
        kind: str,
        bookmarked: bool,
    ) -> list[list[dict]]:
        cid = concept_id[:40]
        rows: list[list[dict]] = []

        if page_count > 1:
            nav: list[dict] = []
            if page_index > 0:
                nav.append({"text": "‹ Prev", "callback_data": f"pg:{cid}:{page_index - 1}"})
            nav.append({"text": f"{page_index + 1}/{page_count}", "callback_data": f"noop:{cid}"})
            if page_index < page_count - 1:
                nav.append({"text": "Next ›", "callback_data": f"pg:{cid}:{page_index + 1}"})
            rows.append(nav)

        if kind == "overview":
            actions: list[dict] = []
            if has_details and page_count > 1:
                actions.append({"text": "Deep dive", "callback_data": f"deep:{cid}"})
            actions.append({"text": "Quiz me", "callback_data": f"quiz:{cid}"})
            rows.append(actions)
            # Second row: library actions (max 3)
            save_label = "Saved" if bookmarked else "Save"
            rows.append(
                [
                    {"text": save_label, "callback_data": f"bm:{cid}"},
                    {"text": "Cards", "callback_data": f"cards:{cid}"},
                    {"text": "Cite", "callback_data": f"cite:{cid}"},
                ]
            )

        return rows

    @staticmethod
    def render_quiz(
        question: str,
        options: list[str],
        *,
        concept_id: str,
        quiz_token: str,
    ) -> TelegramScreen:
        parts = ["<b>Quick quiz</b>", "", _esc(question), ""]
        labels = "ABCD"
        keyboard: list[list[dict]] = []
        for i, opt in enumerate(options[:4]):
            letter = labels[i] if i < len(labels) else str(i + 1)
            parts.append(f"{letter}. {_esc(opt)}")
            keyboard.append(
                [{"text": letter, "callback_data": f"qa:{concept_id[:20]}:{quiz_token}:{i}"}]
            )
        keyboard.append([{"text": "Back to topic", "callback_data": f"pg:{concept_id[:40]}:0"}])
        return TelegramScreen(html="\n".join(parts), inline_keyboard=keyboard)

    @staticmethod
    def render_quiz_result(
        *,
        correct: bool,
        explanation: str,
        concept_id: str,
    ) -> TelegramScreen:
        title = "Correct" if correct else "Not quite"
        body = f"<b>{title}</b>"
        if explanation:
            body += f"\n\n{_esc(explanation)}"
        keyboard = [[{"text": "Back to topic", "callback_data": f"pg:{concept_id[:40]}:0"}]]
        return TelegramScreen(html=body, inline_keyboard=keyboard)

    @staticmethod
    def render_flashcard(
        front: str,
        *,
        card_id: int,
        remaining: int,
        revealed: bool = False,
        back: str = "",
    ) -> TelegramScreen:
        if not revealed:
            html_msg = f"<b>Flashcard</b> · {remaining} due\n\n{_esc(front)}"
            keyboard = [
                [{"text": "Show answer", "callback_data": f"fcshow:{card_id}"}],
            ]
        else:
            html_msg = (
                f"<b>Flashcard</b>\n\n{_esc(front)}\n\n"
                f"<blockquote>{_esc(back)}</blockquote>"
            )
            keyboard = [
                [
                    {"text": "Again", "callback_data": f"fcr:{card_id}:0"},
                    {"text": "Hard", "callback_data": f"fcr:{card_id}:1"},
                    {"text": "Good", "callback_data": f"fcr:{card_id}:2"},
                    {"text": "Easy", "callback_data": f"fcr:{card_id}:3"},
                ]
            ]
        return TelegramScreen(html=html_msg, inline_keyboard=keyboard)

    @staticmethod
    def chunk_html(html_text: str, max_chars: int) -> list[str]:
        if len(html_text) <= max_chars:
            return [html_text]
        chunks: list[str] = []
        remaining = html_text
        while remaining:
            if len(remaining) <= max_chars:
                chunks.append(remaining)
                break
            window = remaining[:max_chars]
            cut = window.rfind("\n\n")
            if cut < max_chars // 3:
                cut = window.rfind("\n")
            if cut < max_chars // 3:
                cut = window.rfind(" ")
            if cut < max_chars // 3:
                cut = max_chars
            chunks.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
        return chunks or [html_text]
