"""Dense + BM25 hybrid fusion (Reciprocal Rank Fusion).

Works with pure dense Pinecone indexes: pull a wider dense candidate set,
score candidates with lexical BM25-ish term overlap, fuse ranks.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-\+/]{1,}", re.I)

# Light medical synonym boost (query expansion for lexical side)
_SYNONYMS: dict[str, list[str]] = {
    "htn": ["hypertension", "high blood pressure"],
    "hypertension": ["htn"],
    "mi": ["myocardial infarction", "heart attack"],
    "heart attack": ["myocardial infarction", "mi"],
    "dm": ["diabetes", "diabetes mellitus"],
    "diabetes": ["dm", "diabetes mellitus"],
    "copd": ["chronic obstructive pulmonary disease"],
    "uti": ["urinary tract infection"],
    "cva": ["stroke", "cerebrovascular"],
    "stroke": ["cva", "cerebrovascular"],
    "chf": ["heart failure", "cardiac failure"],
    "gfr": ["egfr", "glomerular filtration"],
    "bp": ["blood pressure"],
}


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def expand_query_terms(query: str) -> list[str]:
    terms = tokenize(query)
    extra: list[str] = []
    qlow = (query or "").lower()
    for key, syns in _SYNONYMS.items():
        if key in qlow or key in terms:
            for s in syns:
                extra.extend(tokenize(s))
    # unique preserve order
    seen = set()
    out = []
    for t in terms + extra:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def bm25_scores(
    query_terms: list[str],
    docs: list[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    if not docs or not query_terms:
        return [0.0] * len(docs)

    tokenized = [tokenize(d) for d in docs]
    N = len(tokenized)
    avgdl = sum(len(t) for t in tokenized) / max(N, 1)
    df: Counter[str] = Counter()
    for toks in tokenized:
        df.update(set(toks))

    scores: list[float] = []
    for toks in tokenized:
        tf = Counter(toks)
        dl = len(toks) or 1
        s = 0.0
        for term in query_terms:
            if term not in tf:
                continue
            n_q = df.get(term, 0)
            idf = math.log(1 + (N - n_q + 0.5) / (n_q + 0.5))
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * dl / avgdl)
            s += idf * (freq * (k1 + 1)) / denom
        scores.append(s)
    return scores


def rrf_fuse(
    ranked_lists: list[list[int]],
    *,
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion over lists of document indices (best-first)."""
    weights = weights or [1.0] * len(ranked_lists)
    scores: dict[int, float] = {}
    for w, ranking in zip(weights, ranked_lists):
        for rank, doc_idx in enumerate(ranking):
            scores[doc_idx] = scores.get(doc_idx, 0.0) + w * (1.0 / (k + rank + 1))
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def hybrid_rerank(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_k: int = 4,
    alpha: float = 0.65,
) -> list[dict[str, Any]]:
    """
    candidates: list of {score, id, metadata, text?}
    alpha: weight for dense rank (1-alpha for BM25 rank)
    """
    if not candidates:
        return []
    if len(candidates) == 1:
        return candidates[:top_k]

    texts = []
    for c in candidates:
        meta = c.get("metadata") or {}
        texts.append(str(c.get("text") or meta.get("text") or meta.get("content") or ""))

    # Dense rank by existing score
    dense_order = sorted(
        range(len(candidates)),
        key=lambda i: float(candidates[i].get("score") or 0),
        reverse=True,
    )
    q_terms = expand_query_terms(query)
    bm = bm25_scores(q_terms, texts)
    lexical_order = sorted(range(len(candidates)), key=lambda i: bm[i], reverse=True)

    fused = rrf_fuse(
        [dense_order, lexical_order],
        weights=[alpha, 1.0 - alpha],
    )

    out: list[dict[str, Any]] = []
    for idx, fuse_score in fused[:top_k]:
        item = dict(candidates[idx])
        item["hybrid_score"] = fuse_score
        item["bm25_score"] = bm[idx]
        out.append(item)
    return out
