"""ADHD-first Telegram renderer: classic HTML + Bot API 10.x rich Markdown."""

from __future__ import annotations

import html
import re

from interfaces import TelegramScreen


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _md_escape_cell(text: str) -> str:
    """Escape pipe chars so markdown tables don't break."""
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


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


def _body_lines_md(text: str) -> str:
    """Plain body → markdown paragraphs / bullets."""
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
            out.append(f"- {line[2:].strip()}")
        else:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _blockquote_md(text: str) -> str:
    lines = [ln.strip() for ln in str(text or "").split("\n") if ln.strip()]
    if not lines:
        return ""
    return "\n".join(f"> {ln}" for ln in lines)


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
            err = page.get("data") or "Unknown error"
            body = f"<b>Couldn’t answer</b>\n\n{_esc(err)}"
            md = f"# Couldn't answer\n\n{err}"
            return TelegramScreen(
                html=body,
                rich_markdown=md,
                inline_keyboard=[],
                page_index=0,
                page_count=1,
            )

        parts: list[str] = []
        md_parts: list[str] = []

        if kind == "overview":
            title = page.get("title") or "Topic"
            mode = (page.get("mode_label") or "").strip()
            head = f"<b>{_esc(title)}</b>"
            if mode:
                head += f"\n{_esc(mode)}"
            parts.append(head)
            md_parts.append(f"# {_md_escape_cell(title)}")
            if mode:
                md_parts.append(f"*{mode}*")

            banner = (page.get("emergency_banner") or "").strip()
            if banner:
                parts.append("")
                parts.append(f"<blockquote>{_esc(banner)}</blockquote>")
                md_parts.append(_blockquote_md(f"**Alert** — {banner}"))

            summary = (page.get("summary") or "").strip()
            if summary:
                parts.append("")
                parts.append(_esc(summary))
                md_parts.append(summary)

            facts = page.get("facts") or []
            if facts:
                parts.append("")
                md_parts.append("## Key facts")
                for fact in facts[:3]:
                    parts.append(f"• {_esc(fact)}")
                    md_parts.append(f"- {fact}")

            disc = (page.get("disclaimer") or "").strip()
            if disc:
                parts.append("")
                parts.append(f"<blockquote>{_esc(disc)}</blockquote>")
                md_parts.append(_blockquote_md(disc))

        elif kind == "section":
            heading = page.get("heading") or "Details"
            parts.append(f"<b>{_esc(heading)}</b>")
            parts.append("")
            parts.append(_body_lines(page.get("body") or ""))
            md_parts.append(f"## {_md_escape_cell(heading)}")
            md_parts.append(_body_lines_md(page.get("body") or ""))

        elif kind == "citations":
            parts.append("<b>Sources in this library</b>")
            parts.append("")
            md_parts.append("# Sources in this library")
            rows_md = [
                "| Ref | Book | Page | Score |",
                "| --- | --- | --- | --- |",
            ]
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
                rows_md.append(
                    f"| [{_md_escape_cell(ref)}] "
                    f"| {_md_escape_cell(book)} "
                    f"| {_md_escape_cell(page_n)} "
                    f"| {_md_escape_cell(f'{float(score):.3f}')} |"
                )
                excerpt = (c.get("excerpt") or "").strip()
                if excerpt:
                    parts.append(f"<blockquote>{_esc(excerpt[:220])}</blockquote>")
                    md_parts.append(
                        f"<details>\n<summary>[{ref}] excerpt</summary>\n\n"
                        f"{excerpt[:400]}\n\n</details>"
                    )
                parts.append("")
            md_parts.append("\n".join(rows_md))

        elif kind == "source":
            parts.append("<b>Primary citation</b>")
            parts.append("")
            src = page.get("source") or "Textbook"
            parts.append(f"<blockquote>{_esc(src)}</blockquote>")
            md_parts.append("# Primary citation")
            md_parts.append(_blockquote_md(src))
            disc = (page.get("disclaimer") or "").strip()
            if disc:
                parts.append("")
                parts.append(_esc(disc))
                md_parts.append(disc)
        else:
            parts.append(_esc(str(page)))
            md_parts.append(str(page))

        html_msg = "\n".join(parts).strip()
        rich_md = "\n\n".join(p for p in md_parts if p is not None and str(p).strip()).strip()
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
            rich_markdown=rich_md or None,
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
            save_label = "Saved" if bookmarked else "Save"
            rows.append(
                [
                    {"text": save_label, "callback_data": f"bm:{cid}"},
                    {"text": "Cards", "callback_data": f"cards:{cid}"},
                    {"text": "Cite", "callback_data": f"cite:{cid}"},
                ]
            )
            rows.append([{"text": "Menu", "callback_data": "menu:main"}])

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
        md_parts = ["# Quick quiz", question, ""]
        labels = "ABCD"
        keyboard: list[list[dict]] = []
        for i, opt in enumerate(options[:4]):
            letter = labels[i] if i < len(labels) else str(i + 1)
            parts.append(f"{letter}. {_esc(opt)}")
            md_parts.append(f"{i + 1}. **{letter}.** {opt}")
            keyboard.append(
                [{"text": letter, "callback_data": f"qa:{concept_id[:20]}:{quiz_token}:{i}"}]
            )
        keyboard.append([{"text": "Back to topic", "callback_data": f"pg:{concept_id[:40]}:0"}])
        return TelegramScreen(
            html="\n".join(parts),
            rich_markdown="\n\n".join(md_parts),
            inline_keyboard=keyboard,
        )

    @staticmethod
    def render_quiz_result(
        *,
        correct: bool,
        explanation: str,
        concept_id: str,
    ) -> TelegramScreen:
        title = "Correct" if correct else "Not quite"
        body = f"<b>{title}</b>"
        md = f"# {title}"
        if explanation:
            body += f"\n\n{_esc(explanation)}"
            md += f"\n\n{explanation}"
        keyboard = [[{"text": "Back to topic", "callback_data": f"pg:{concept_id[:40]}:0"}]]
        return TelegramScreen(html=body, rich_markdown=md, inline_keyboard=keyboard)

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
            md = f"# Flashcard · {remaining} due\n\n{front}"
            keyboard = [
                [{"text": "Show answer", "callback_data": f"fcshow:{card_id}"}],
            ]
        else:
            html_msg = (
                f"<b>Flashcard</b>\n\n{_esc(front)}\n\n"
                f"<blockquote>{_esc(back)}</blockquote>"
            )
            md = f"# Flashcard\n\n{front}\n\n{_blockquote_md(back)}"
            keyboard = [
                [
                    {"text": "Again", "callback_data": f"fcr:{card_id}:0"},
                    {"text": "Hard", "callback_data": f"fcr:{card_id}:1"},
                    {"text": "Good", "callback_data": f"fcr:{card_id}:2"},
                    {"text": "Easy", "callback_data": f"fcr:{card_id}:3"},
                ]
            ]
        return TelegramScreen(html=html_msg, rich_markdown=md, inline_keyboard=keyboard)

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
