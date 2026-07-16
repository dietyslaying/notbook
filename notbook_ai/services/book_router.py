"""Namespace / book router: pick which Pinecone namespaces to search.

Two signals:
  1) Lexical score of the query against the book/namespace name
  2) Optional dense probe scores (top_k=1 per namespace) passed in from retrieve

Falls back to all namespaces when confidence is low.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from services.hybrid_search import expand_query_terms, tokenize

logger = logging.getLogger(__name__)

# Light domain hints when book titles don't contain the query term
_DOMAIN_HINTS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(anatomy|plexus|muscle|nerve|bone|ligament|fossa|artery|vein)\b", re.I),
     ["anatomy", "gray", "snell", "netter"]),
    (re.compile(r"\b(pharmacolog|drug|dose|mg\b|tablet|antibiotic|statin|ssri|metformin|insulin)\b", re.I),
     ["pharmacolog", "katzung", "drug", "prescrib", "bnf"]),
    (re.compile(r"\b(patholog|histolog|biopsy|neoplasm|carcinoma)\b", re.I),
     ["patholog", "robbins", "histolog"]),
    (re.compile(r"\b(physiol|homeostasis|action potential)\b", re.I),
     ["physiol", "guyton", "ganong"]),
    (re.compile(r"\b(general practice|primary care|gp\b|family medicine|murtagh)\b", re.I),
     ["murtagh", "general practice", "primary", "family"]),
    (re.compile(r"\b(surg|operative|laparoscop)\b", re.I),
     ["surg", "bailey", "operative"]),
    (re.compile(r"\b(pediatr|paediatr|neonat|child)\b", re.I),
     ["pediatr", "paediatr", "nelson", "child"]),
    (re.compile(r"\b(psychiatr|depression|psychosis|anxiety disorder)\b", re.I),
     ["psychiatr", "kaplan", "mental"]),
    (re.compile(r"\b(obstetric|gynaec|gynec|pregnan|labour|labor)\b", re.I),
     ["obstetric", "gynaec", "gynec", "midwif"]),
]


def _display_name(namespace: str) -> str:
    ns = (namespace or "").strip()
    if "|" in ns:
        return ns.split("|", 1)[1].strip() or ns
    return ns


def _ns_blob(namespace: str) -> str:
    name = _display_name(namespace).lower()
    raw = namespace.lower().replace("|", " ").replace("_", " ").replace("-", " ")
    return f"{name} {raw}"


def _ns_tokens(namespace: str) -> set[str]:
    tokens = set(tokenize(_ns_blob(namespace)))
    tokens -= {"global", "book", "pdf", "edition", "vol", "volume", "the", "and", "user"}
    return tokens


@dataclass
class RouteResult:
    namespaces: list[str]
    scores: dict[str, float]
    strategy: str  # "routed" | "all" | "single" | "empty" | "probed"
    reason: str


class BookRouter:
    def __init__(
        self,
        *,
        max_namespaces: int = 3,
        min_score: float = 0.12,
        always_include_top: int = 1,
        fallback_to_all: bool = True,
        probe_weight: float = 0.75,
    ) -> None:
        self.max_namespaces = max(1, int(max_namespaces))
        self.min_score = float(min_score)
        self.always_include_top = max(0, int(always_include_top))
        self.fallback_to_all = bool(fallback_to_all)
        self.probe_weight = min(1.0, max(0.0, float(probe_weight)))

    def score_namespace_lexical(self, query: str, namespace: str) -> float:
        q_terms = expand_query_terms(query)
        if not q_terms:
            return 0.0
        ns_toks = _ns_tokens(namespace)
        blob = _ns_blob(namespace)
        if not ns_toks and not blob:
            return 0.0

        q_set = set(q_terms)
        overlap = len(q_set & ns_toks)
        jacc = overlap / max(len(q_set), 1)

        substr = 0.0
        for t in q_terms:
            if len(t) >= 4 and t in blob:
                substr += 1.0
        substr_n = min(1.0, substr / max(len(q_terms), 1))

        # Domain hint boost (query pattern → book-name keywords)
        domain = 0.0
        for pat, keys in _DOMAIN_HINTS:
            if pat.search(query or ""):
                if any(k in blob for k in keys):
                    domain = max(domain, 0.55)
                # partial
                elif any(k[:5] in blob for k in keys if len(k) >= 5):
                    domain = max(domain, 0.35)

        name = _display_name(namespace).lower()
        phrase = 0.35 if len(name) >= 6 and name in (query or "").lower() else 0.0

        score = (0.40 * jacc) + (0.25 * substr_n) + (0.30 * domain) + phrase
        return round(min(1.0, score), 4)

    def route(
        self,
        query: str,
        all_namespaces: list[str],
        *,
        probe_scores: Optional[dict[str, float]] = None,
    ) -> RouteResult:
        namespaces = [ns for ns in all_namespaces if ns is not None]
        if not namespaces:
            return RouteResult([], {}, "empty", "no namespaces")

        if len(namespaces) == 1:
            return RouteResult(
                namespaces, {namespaces[0]: 1.0}, "single", "only one book namespace"
            )

        lex = {ns: self.score_namespace_lexical(query, ns) for ns in namespaces}

        # Normalize probe scores to 0–1 if provided
        probes: dict[str, float] = {}
        if probe_scores:
            vals = [float(v) for v in probe_scores.values() if v is not None]
            mx = max(vals) if vals else 0.0
            mn = min(vals) if vals else 0.0
            span = (mx - mn) or 1.0
            for ns, v in probe_scores.items():
                if ns not in lex:
                    continue
                raw = float(v or 0.0)
                # cosine-ish scores often already 0–1; still min-max for ranking
                probes[ns] = (raw - mn) / span if mx > mn else raw

        scores: dict[str, float] = {}
        pw = self.probe_weight if probes else 0.0
        for ns in namespaces:
            l = lex.get(ns, 0.0)
            p = probes.get(ns, 0.0)
            if probes:
                scores[ns] = round((1.0 - pw) * l + pw * p, 4)
            else:
                scores[ns] = l

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best = ranked[0][1] if ranked else 0.0

        chosen: list[str] = []
        for ns, sc in ranked:
            if sc >= self.min_score and len(chosen) < self.max_namespaces:
                chosen.append(ns)

        if self.always_include_top and ranked:
            for ns, _ in ranked[: self.always_include_top]:
                if ns not in chosen:
                    chosen.append(ns)
            chosen = chosen[: self.max_namespaces]

        strategy = "probed" if probes else "routed"

        # Low confidence → all books
        if self.fallback_to_all and best < self.min_score:
            logger.info(
                "book_router fallback_to_all best=%.3f min=%.3f", best, self.min_score
            )
            return RouteResult(
                namespaces,
                scores,
                "all",
                f"low confidence (best={best:.3f}); searching all books",
            )

        if not chosen:
            if self.fallback_to_all:
                return RouteResult(
                    namespaces, scores, "all", "no route match; searching all"
                )
            chosen = [ranked[0][0]]

        logger.info(
            "book_router strategy=%s n=%s/%s top=%s",
            strategy,
            len(chosen),
            len(namespaces),
            [(_display_name(n), scores[n]) for n in chosen],
        )
        return RouteResult(
            chosen,
            scores,
            strategy,
            f"selected {len(chosen)} of {len(namespaces)} namespaces",
        )


def router_from_config(pinecone_cfg: Optional[dict] = None) -> BookRouter:
    cfg = pinecone_cfg or {}
    rcfg = cfg.get("router") if isinstance(cfg.get("router"), dict) else {}
    return BookRouter(
        max_namespaces=int(rcfg.get("max_namespaces", cfg.get("router_max_namespaces", 3))),
        min_score=float(rcfg.get("min_score", cfg.get("router_min_score", 0.12))),
        always_include_top=int(
            rcfg.get("always_include_top", cfg.get("router_always_include_top", 1))
        ),
        fallback_to_all=bool(
            rcfg.get("fallback_to_all", cfg.get("router_fallback_to_all", True))
        ),
        probe_weight=float(rcfg.get("probe_weight", 0.75)),
    )
