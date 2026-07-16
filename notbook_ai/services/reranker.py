"""Rerank retrieved chunks before LLM context assembly.

Backends:
  - cross_encoder: BAAI/bge-reranker-v2-m3 via sentence-transformers (optional)
  - gemini: listwise ranking with Gemini Flash (default, no extra deps)
  - none: passthrough

Pipeline position: dense+hybrid pool → rerank → top_k_final
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from config import config

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self) -> None:
        cfg = config.raw_config.get("reranker") or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.backend = str(cfg.get("backend") or "auto").lower()
        self.model = str(cfg.get("model") or "BAAI/bge-reranker-v2-m3")
        self.candidate_k = int(cfg.get("candidate_k") or 12)
        self.top_k = int(cfg.get("top_k") or 4)
        self._ce = None  # lazy cross-encoder
        self._resolved: Optional[str] = None

    def _resolve_backend(self) -> str:
        if self._resolved:
            return self._resolved
        if not self.enabled or self.backend == "none":
            self._resolved = "none"
            return self._resolved
        if self.backend == "cross_encoder":
            self._resolved = "cross_encoder" if self._load_ce() else "gemini"
            return self._resolved
        if self.backend == "gemini":
            self._resolved = "gemini"
            return self._resolved
        # auto: prefer local CE if installed, else gemini
        if self._load_ce():
            self._resolved = "cross_encoder"
        else:
            self._resolved = "gemini"
        return self._resolved

    def _load_ce(self) -> bool:
        if self._ce is not None:
            return True
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            logger.info("Loading cross-encoder %s …", self.model)
            self._ce = CrossEncoder(self.model)
            return True
        except Exception as e:
            logger.info("Cross-encoder unavailable (%s); will use Gemini rerank", e)
            self._ce = None
            return False

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        top_k: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Return candidates sorted best-first, truncated to top_k."""
        if not candidates:
            return []
        k = top_k if top_k is not None else self.top_k
        pool = candidates[: max(self.candidate_k, k)]
        backend = self._resolve_backend()

        if backend == "none" or len(pool) <= 1:
            return pool[:k]

        try:
            if backend == "cross_encoder":
                ranked = self._rerank_cross_encoder(query, pool)
            else:
                ranked = await self._rerank_gemini(query, pool)
            return ranked[:k]
        except Exception as e:
            logger.warning("Rerank failed (%s); keeping hybrid order", e)
            return pool[:k]

    def _rerank_cross_encoder(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        assert self._ce is not None
        pairs = []
        for c in candidates:
            text = str(c.get("text") or (c.get("metadata") or {}).get("text") or "")
            pairs.append([query, text[:1200]])
        scores = self._ce.predict(pairs)
        scored = []
        for c, sc in zip(candidates, scores):
            item = dict(c)
            item["rerank_score"] = float(sc)
            scored.append(item)
        scored.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        return scored

    async def _rerank_gemini(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        from services.gemini_client import gemini_client

        lines = []
        for i, c in enumerate(candidates):
            text = str(c.get("text") or (c.get("metadata") or {}).get("text") or "")
            text = re.sub(r"\s+", " ", text)[:350]
            book = (c.get("metadata") or {}).get("book") or ""
            page = (c.get("metadata") or {}).get("page") or ""
            lines.append(f"[{i}] ({book} p.{page}) {text}")

        prompt = f"""You rank textbook excerpts for relevance to a medical study question.
Return JSON only: {{"order": [best_index, second_best, ...]}}
Use each index at most once. Rank ALL given indices from most to least relevant.
Only use relevance to the question — not length or writing style.

QUESTION:
{query}

EXCERPTS:
{chr(10).join(lines)}
"""
        raw = await gemini_client.generate(prompt, json_mode=True)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
        data = json.loads(raw)
        order = data.get("order") if isinstance(data, dict) else None
        if not isinstance(order, list) or not order:
            return candidates

        seen = set()
        ranked: list[dict[str, Any]] = []
        for idx in order:
            try:
                i = int(idx)
            except (TypeError, ValueError):
                continue
            if i < 0 or i >= len(candidates) or i in seen:
                continue
            seen.add(i)
            item = dict(candidates[i])
            item["rerank_score"] = float(len(candidates) - len(ranked))
            ranked.append(item)
        # Append any missing (stable)
        for i, c in enumerate(candidates):
            if i not in seen:
                item = dict(c)
                item["rerank_score"] = 0.0
                ranked.append(item)
        return ranked


reranker = Reranker()
