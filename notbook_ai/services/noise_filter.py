"""ADHD noise filter: strip clutter from RAG chunks and LLM structured output.

Design goals (also good for everyone):
- Short lines, plain language, no decorative spam
- No markdown asterisks / raw HTML from the model
- Hard caps on facts, sections, paragraph length
- Remove empty fluff and filler phrases
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from config import config
from interfaces import DetailSection, NDMDocument


_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NL = re.compile(r"\n{3,}")
_BULLET_PREFIX = re.compile(r"^[\s]*([•\-\*\u2022▪►●]|\d+[.)])\s+")
# Broad emoji / pictograph ranges (optional strip)
_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U00002700-\U000027BF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


def _adhd_cfg() -> dict:
    return config.raw_config.get("adhd") or {}


def clean_plain_text(text: str, *, strip_emojis: bool | None = None) -> str:
    """Normalize a free-text field into ADHD-friendly plain text."""
    if not text:
        return ""

    cfg = _adhd_cfg()
    if strip_emojis is None:
        strip_emojis = bool(cfg.get("strip_emojis", True))

    t = unicodedata.normalize("NFKC", str(text))
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = _HTML_TAG.sub("", t)
    t = _MD_BOLD.sub(r"\1", t)
    t = _MD_ITALIC.sub(r"\1", t)
    t = _MD_CODE.sub(r"\1", t)
    t = _MD_HEADING.sub("", t)
    t = t.replace("*", "").replace("_", " ")
    if strip_emojis:
        t = _EMOJI.sub("", t)

    # Drop filler phrases (case-insensitive)
    for phrase in cfg.get("filler_phrases") or []:
        if not phrase:
            continue
        t = re.sub(re.escape(phrase), " ", t, flags=re.IGNORECASE)

    # Normalize list markers to plain dashes for intermediate form
    lines = []
    for line in t.split("\n"):
        line = _BULLET_PREFIX.sub("- ", line.strip())
        line = _MULTI_SPACE.sub(" ", line).strip()
        # Clean spaces before punctuation left by filler removal
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        if line:
            lines.append(line)
    t = "\n".join(lines)
    t = _MULTI_NL.sub("\n\n", t).strip()
    return t


def _split_paragraphs(text: str, max_para: int) -> str:
    """Break long walls of text into short paragraphs."""
    text = clean_plain_text(text)
    if not text:
        return ""

    # Prefer existing newlines / sentences
    chunks: list[str] = []
    for block in re.split(r"\n+", text):
        block = block.strip()
        if not block:
            continue
        if len(block) <= max_para:
            chunks.append(block)
            continue
        # Sentence-ish split
        sentences = re.split(r"(?<=[.!?])\s+", block)
        buf = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if not buf:
                buf = s
            elif len(buf) + 1 + len(s) <= max_para:
                buf = f"{buf} {s}"
            else:
                chunks.append(buf)
                buf = s
        if buf:
            chunks.append(buf)
    return "\n\n".join(chunks)


def clean_rag_context(raw: str, *, max_chars: int = 6000) -> str:
    """Strip noise from retrieved textbook excerpts before they hit the LLM."""
    cleaned = clean_plain_text(raw, strip_emojis=True)
    # Collapse decorative separators
    cleaned = re.sub(r"[-=_]{4,}", "---", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return cleaned


def _trim(s: str, n: int) -> str:
    s = s.strip()
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "…"


def filter_ndm_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Apply hard ADHD caps and noise filter to a raw NDM-like dict."""
    cfg = _adhd_cfg()
    max_summary = int(cfg.get("max_summary_chars", 280))
    max_facts = int(cfg.get("max_facts", 3))
    max_fact = int(cfg.get("max_fact_chars", 90))
    max_section = int(cfg.get("max_section_chars", 900))
    max_sections = int(cfg.get("max_sections", 5))
    max_para = int(cfg.get("max_paragraph_chars", 160))

    title = _trim(clean_plain_text(data.get("title") or "Topic"), 120)
    summary = _trim(
        _split_paragraphs(str(data.get("summary") or ""), max_para).replace("\n\n", " "),
        max_summary,
    )

    raw_facts = data.get("core_facts") or []
    if isinstance(raw_facts, str):
        raw_facts = [raw_facts]
    facts: list[str] = []
    for f in raw_facts:
        f = _trim(clean_plain_text(str(f)), max_fact)
        if f and f not in facts:
            facts.append(f)
        if len(facts) >= max_facts:
            break

    sections_in = data.get("detail_sections") or []
    # Back-compat: single expandable_details blob → one section
    if not sections_in and data.get("expandable_details"):
        sections_in = [{"heading": "Details", "body": data["expandable_details"]}]

    sections: list[dict[str, str]] = []
    for sec in sections_in[:max_sections]:
        if isinstance(sec, DetailSection):
            heading, body = sec.heading, sec.body
        elif isinstance(sec, dict):
            heading = sec.get("heading") or sec.get("title") or "Details"
            body = sec.get("body") or sec.get("content") or ""
        else:
            continue
        heading = _trim(clean_plain_text(str(heading)), 80)
        body = _trim(_split_paragraphs(str(body), max_para), max_section)
        if heading and body:
            sections.append({"heading": heading, "body": body})

    source = _trim(
        clean_plain_text(data.get("source_citation") or "Textbook excerpt"),
        200,
    )

    return {
        "title": title or "Topic",
        "summary": summary,
        "core_facts": facts,
        "detail_sections": sections,
        "source_citation": source,
    }


def filter_ndm_document(doc: NDMDocument) -> NDMDocument:
    cleaned = filter_ndm_dict(doc.model_dump())
    return NDMDocument(**cleaned)


def strip_for_quiz_stem(text: str, max_len: int = 200) -> str:
    return _trim(clean_plain_text(text), max_len)
