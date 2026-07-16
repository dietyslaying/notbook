"""Faithfulness gate: keep answers grounded in retrieved textbook chunks only.

Checks:
  1) citations_used only reference real retrieved refs (c1, c2, …)
  2) core_facts / section lines have enough lexical overlap with source excerpts
  3) if content is too weakly grounded → strip or fail closed

Does not invent medical content; only filters/annotates model output.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from services.hybrid_search import tokenize

logger = logging.getLogger(__name__)

_REF = re.compile(r"\bc(\d+)\b", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _content_tokens(text: str) -> set[str]:
    """Tokens useful for grounding (drop tiny stop-ish tokens)."""
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "are", "was",
        "were", "have", "has", "had", "not", "but", "may", "can", "use",
        "used", "also", "than", "into", "over", "under", "such", "more",
        "most", "some", "any", "all", "per", "via",
    }
    return {t for t in tokenize(text) if len(t) > 2 and t not in stop}


def claim_grounding_score(claim: str, corpus: str) -> float:
    """0–1 score: fraction of claim content tokens found in corpus."""
    claim_toks = _content_tokens(claim)
    if not claim_toks:
        # Number-only claim: check numbers appear in corpus
        nums = _NUMBER.findall(claim or "")
        if not nums:
            return 0.0
        c = _norm(corpus)
        hits = sum(1 for n in nums if n in c)
        return hits / len(nums)

    corpus_toks = _content_tokens(corpus)
    if not corpus_toks:
        return 0.0
    hits = len(claim_toks & corpus_toks)
    base = hits / len(claim_toks)

    # Boost if distinctive numbers from claim appear in corpus
    nums = _NUMBER.findall(claim or "")
    if nums:
        c = _norm(corpus)
        n_hits = sum(1 for n in nums if n in c)
        base = max(base, 0.5 * base + 0.5 * (n_hits / len(nums)))
    return round(min(1.0, base), 4)


def build_corpus(citations: list[dict[str, Any]]) -> str:
    parts = []
    for c in citations or []:
        parts.append(str(c.get("excerpt") or ""))
        parts.append(str(c.get("book") or ""))
        parts.append(str(c.get("page") or ""))
    return "\n".join(parts)


def valid_refs(citations: list[dict[str, Any]]) -> set[str]:
    refs = set()
    for c in citations or []:
        ref = str(c.get("ref") or "").strip().lower()
        if ref:
            refs.add(ref)
        # Also accept cN pattern from ref field
        m = _REF.search(ref)
        if m:
            refs.add(f"c{m.group(1)}")
    # Normalize to c1, c2 form
    out = set()
    for r in refs:
        m = _REF.fullmatch(r) or _REF.search(r)
        if m:
            out.add(f"c{m.group(1)}")
        elif r.startswith("c") and r[1:].isdigit():
            out.add(r.lower())
    # If citations have ordered refs, ensure c1..cn
    for i, _c in enumerate(citations or [], start=1):
        out.add(f"c{i}")
    return out


def normalize_citations_used(
    used: Any, citations: list[dict[str, Any]]
) -> list[str]:
    allowed = valid_refs(citations)
    if not allowed:
        return []
    raw: list[str] = []
    if isinstance(used, str):
        raw = _REF.findall(used) or [used]
        raw = [f"c{x}" if x.isdigit() else str(x).lower() for x in raw]
    elif isinstance(used, list):
        for item in used:
            s = str(item).strip().lower()
            m = _REF.search(s)
            if m:
                raw.append(f"c{m.group(1)}")
            elif s in allowed:
                raw.append(s)
    # Keep only allowed, unique, order preserved
    out: list[str] = []
    for r in raw:
        if r in allowed and r not in out:
            out.append(r)
    return out


def auto_assign_citations(
    text_blob: str, citations: list[dict[str, Any]], *, max_refs: int = 3
) -> list[str]:
    """Pick retrieved chunks that best overlap the final answer text."""
    if not citations:
        return []
    scored: list[tuple[str, float]] = []
    for i, c in enumerate(citations, start=1):
        ref = str(c.get("ref") or f"c{i}").lower()
        if not ref.startswith("c"):
            ref = f"c{i}"
        excerpt = str(c.get("excerpt") or "")
        sc = claim_grounding_score(text_blob, excerpt)
        # Also reverse: excerpt tokens in answer
        sc = max(sc, claim_grounding_score(excerpt[:200], text_blob) * 0.8)
        scored.append((ref, sc))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, sc in scored if sc >= 0.12][:max_refs] or (
        [scored[0][0]] if scored else []
    )


@dataclass
class FaithfulnessResult:
    ok: bool
    ndm: dict[str, Any]
    dropped_facts: list[str] = field(default_factory=list)
    dropped_sections: int = 0
    citations_used: list[str] = field(default_factory=list)
    grounding_score: float = 0.0
    notes: list[str] = field(default_factory=list)
    needs_retry: bool = False
    fail_reason: str = ""


def apply_faithfulness_gate(
    ndm: dict[str, Any],
    citations: list[dict[str, Any]],
    *,
    min_claim_score: float = 0.28,
    min_overall_score: float = 0.22,
    min_facts_keep: int = 0,
    strict: bool = True,
) -> FaithfulnessResult:
    """
    Filter NDM against citations. Returns updated ndm dict (copy-ish).
    """
    if "error" in ndm:
        return FaithfulnessResult(ok=False, ndm=ndm, fail_reason=ndm["error"])

    data = dict(ndm)
    corpus = build_corpus(citations)
    if not corpus.strip() or not citations:
        return FaithfulnessResult(
            ok=False,
            ndm={
                "error": (
                    "No textbook excerpts were available to ground an answer. "
                    "Try different wording."
                )
            },
            fail_reason="empty_citations",
            needs_retry=False,
        )

    # --- citations_used ---
    used = normalize_citations_used(data.get("citations_used"), citations)
    answer_blob = " ".join(
        [
            str(data.get("title") or ""),
            str(data.get("summary") or ""),
            " ".join(str(f) for f in (data.get("core_facts") or [])),
            " ".join(
                f"{s.get('heading','')} {s.get('body','')}"
                for s in (data.get("detail_sections") or [])
                if isinstance(s, dict)
            ),
        ]
    )
    if not used:
        used = auto_assign_citations(answer_blob, citations)
        notes_pre = ["citations auto-assigned from retrieved chunks"]
    else:
        notes_pre = []

    # --- facts ---
    raw_facts = list(data.get("core_facts") or [])
    kept_facts: list[str] = []
    dropped_facts: list[str] = []
    fact_scores: list[float] = []
    for fact in raw_facts:
        f = str(fact).strip()
        if not f:
            continue
        sc = claim_grounding_score(f, corpus)
        if sc >= min_claim_score:
            kept_facts.append(f)
            fact_scores.append(sc)
        else:
            dropped_facts.append(f)

    # --- sections ---
    kept_sections: list[dict] = []
    dropped_sections = 0
    section_scores: list[float] = []
    for sec in data.get("detail_sections") or []:
        if not isinstance(sec, dict):
            dropped_sections += 1
            continue
        body = str(sec.get("body") or "").strip()
        heading = str(sec.get("heading") or "Details").strip()
        if not body:
            dropped_sections += 1
            continue
        # Score per paragraph / bullet line; keep lines that ground
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        kept_lines: list[str] = []
        for ln in lines:
            sc = claim_grounding_score(ln, corpus)
            if sc >= min_claim_score * 0.85:  # slightly softer for long lines
                kept_lines.append(ln)
                section_scores.append(sc)
        if kept_lines:
            kept_sections.append({"heading": heading, "body": "\n".join(kept_lines)})
        else:
            dropped_sections += 1

    # --- summary ---
    summary = str(data.get("summary") or "").strip()
    sum_score = claim_grounding_score(summary, corpus) if summary else 0.0
    if summary and sum_score < min_claim_score * 0.75:
        # Soften: if we have good facts, rebuild a minimal summary from facts
        if kept_facts:
            summary = kept_facts[0]
            if len(kept_facts) > 1:
                summary = f"{kept_facts[0]} {kept_facts[1]}"
            sum_score = claim_grounding_score(summary, corpus)
            notes_pre.append("summary rebuilt from grounded facts")
        else:
            summary = (
                "The library excerpts did not support a clear short summary for this query."
            )
            sum_score = 1.0  # meta statement
            notes_pre.append("summary replaced — insufficient grounding")

    # Overall score only from *content* that remains grounded (not meta placeholders)
    content_scores = fact_scores + section_scores
    if summary and not summary.startswith("The library excerpts did not support"):
        content_scores = content_scores + [sum_score]
    overall = sum(content_scores) / len(content_scores) if content_scores else 0.0

    data["core_facts"] = kept_facts
    data["detail_sections"] = kept_sections
    data["summary"] = summary
    data["citations_used"] = used
    data["faithfulness"] = {
        "grounding_score": round(overall, 4),
        "dropped_facts": len(dropped_facts),
        "dropped_sections": dropped_sections,
        "citations_used": used,
    }

    has_substance = bool(kept_facts or kept_sections)

    # Fail closed if nothing grounded remains
    if strict and not has_substance:
        return FaithfulnessResult(
            ok=False,
            ndm={
                "error": (
                    "I found library text, but could not ground a reliable answer "
                    "in those excerpts without inventing details. "
                    "Try a more specific term or another book wording."
                )
            },
            dropped_facts=dropped_facts,
            dropped_sections=dropped_sections,
            citations_used=used,
            grounding_score=overall,
            notes=notes_pre + ["fail_closed: no grounded facts/sections"],
            needs_retry=True,
            fail_reason="weak_grounding",
        )

    if strict and overall < min_overall_score:
        return FaithfulnessResult(
            ok=False,
            ndm={
                "error": (
                    "Answer failed the faithfulness check against retrieved textbook chunks. "
                    "Try rephrasing the question."
                )
            },
            dropped_facts=dropped_facts,
            dropped_sections=dropped_sections,
            citations_used=used,
            grounding_score=overall,
            notes=notes_pre,
            needs_retry=True,
            fail_reason="overall_below_threshold",
        )

    # Prefer source_citation from first used chunk
    if used and citations:
        ref_to_c = {
            str(c.get("ref") or f"c{i}").lower(): c
            for i, c in enumerate(citations, start=1)
        }
        # normalize keys
        for i, c in enumerate(citations, start=1):
            ref_to_c[f"c{i}"] = c
        first = ref_to_c.get(used[0])
        if first:
            book = first.get("book") or "Textbook"
            page = first.get("page", "N/A")
            data["source_citation"] = f"{book}, p.{page}"

    ok = True
    notes = notes_pre[:]
    if dropped_facts:
        notes.append(f"dropped {len(dropped_facts)} ungrounded fact(s)")
    if dropped_sections:
        notes.append(f"dropped {dropped_sections} ungrounded section(s)")

    logger.info(
        "faithfulness ok=%s overall=%.3f kept_facts=%s dropped_facts=%s used=%s",
        ok,
        overall,
        len(kept_facts),
        len(dropped_facts),
        used,
    )
    return FaithfulnessResult(
        ok=ok,
        ndm=data,
        dropped_facts=dropped_facts,
        dropped_sections=dropped_sections,
        citations_used=used,
        grounding_score=overall,
        notes=notes,
        needs_retry=False,
    )
