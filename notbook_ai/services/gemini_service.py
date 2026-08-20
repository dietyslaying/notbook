"""RAG + generation: book router, hybrid retrieval, faithfulness gate, google.genai."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from config import config
from core.ndm_validator import NDMValidator
from interfaces import IntentType
from services.book_router import BookRouter, router_from_config
from services.cache_manager import CacheManager
from services.embeddings import embedding_service
from services.faithfulness import apply_faithfulness_gate
from services.gemini_client import gemini_client
from services.hybrid_search import hybrid_rerank
from services.noise_filter import clean_rag_context, strip_for_quiz_stem
from services.reranker import reranker

logger = logging.getLogger(__name__)


_JSON_SCHEMA_HINT = """
Return ONLY valid JSON with this exact shape (no markdown fences):
{
  "title": "Short topic title (max 8 words)",
  "summary": "2 short sentences. Plain text only. No fluff.",
  "core_facts": ["Fact 1 (one line)", "Fact 2", "Fact 3"],
  "detail_sections": [
    {"heading": "Section name", "body": "Short plain paragraphs. Use - for lists."}
  ],
  "source_citation": "Primary book, page",
  "citations_used": ["c1", "c2"]
}

STRICT RULES:
- You compile and restate content from the provided CONTEXT only. Never invent facts, guidelines, or doses.
- Use ONLY the context for medical facts.
- Every core_fact MUST be supportable by one of the [cN] excerpts.
- citations_used MUST only list refs that appear in the context (c1, c2, ...).
- If context is thin or off-topic, say so in the summary. Do not fill gaps from general knowledge.
- NO markdown (* _ ` #), NO HTML, NO emoji.
- Summary: max 2 sentences.
- core_facts: max 3; each under 90 characters; concrete.
- detail_sections: follow the study-mode caps below.
- Answer the USER QUESTION directly.
"""


class GeminiService:
    def __init__(self) -> None:
        llm_cfg = config.raw_config["llm"]
        self.model_name = llm_cfg["model_name"]
        cache_cfg = config.raw_config.get("cache") or {}
        self.cache = CacheManager(
            ttl=int(cache_cfg.get("ttl", 3600)),
            max_entries=int(cache_cfg.get("max_entries", 500)),
        )
        self.pinecone_cfg = config.raw_config.get("pinecone") or {}
        self.faith_cfg = config.raw_config.get("faithfulness") or {}
        # Lazy: do NOT connect to a specific index at import time.
        # Missing index was crashing Render before the health port opened.
        self._pc: Pinecone | None = None
        self._index = None
        self._index_ready = False
        self._ns_cache: tuple[float, list[str]] | None = None
        self._ns_ttl = 300.0
        self.router: BookRouter = router_from_config(self.pinecone_cfg)
        self.index_name = str(
            self.pinecone_cfg.get("index_name") or "library-index-v2"
        )
        self.index_dimension = int(
            self.pinecone_cfg.get("dimension")
            or (config.raw_config.get("embeddings") or {}).get("dimension")
            or 768
        )

    def _client(self) -> Pinecone:
        if self._pc is None:
            self._pc = Pinecone(api_key=config.pinecone_api_key)
        return self._pc

    def _ensure_index(self):
        """Return Pinecone Index; create empty index if it does not exist yet."""
        if self._index is not None and self._index_ready:
            return self._index

        pc = self._client()
        name = self.index_name
        dim = self.index_dimension

        try:
            names = list(pc.list_indexes().names())
        except Exception as e:
            logger.warning("list_indexes failed: %s", e)
            names = []

        if name not in names:
            logger.warning(
                "Pinecone index %r not found — creating (dim=%s). "
                "You still need to ingest PDFs before answers work.",
                name,
                dim,
            )
            try:
                pc.create_index(
                    name=name,
                    dimension=dim,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
                for _ in range(60):
                    try:
                        st = pc.describe_index(name).status
                        if st and st.get("ready"):
                            break
                    except Exception:
                        pass
                    time.sleep(2)
            except Exception as e:
                # Race: another worker may have created it
                logger.warning("create_index %r: %s", name, e)
                try:
                    names = list(pc.list_indexes().names())
                except Exception:
                    names = []
                if name not in names:
                    raise RuntimeError(
                        f"Pinecone index {name!r} missing and could not be created: {e}"
                    ) from e
        else:
            try:
                info = pc.describe_index(name)
                existing = getattr(info, "dimension", None)
                if existing is not None and int(existing) != int(dim):
                    logger.error(
                        "Index %r is %s-d but config wants %s-d. "
                        "Change pinecone.index_name or dimension and re-ingest.",
                        name,
                        existing,
                        dim,
                    )
            except Exception as e:
                logger.debug("describe_index dim check: %s", e)

        self._index = pc.Index(name)
        self._index_ready = True
        logger.info("Pinecone index ready: %s (dim=%s)", name, dim)
        return self._index

    async def generate_json(
        self, prompt: str, max_output_tokens: int | None = None
    ) -> str:
        return await gemini_client.generate(
            prompt, json_mode=True, max_output_tokens=max_output_tokens
        )

    async def _generate_json(self, prompt: str) -> str:
        return await self.generate_json(prompt)

    def _all_namespaces(self) -> list[str]:
        now = time.time()
        if self._ns_cache and now - self._ns_cache[0] < self._ns_ttl:
            return self._ns_cache[1]
        try:
            index = self._ensure_index()
            stats = index.describe_index_stats()
            namespaces = [
                ns
                for ns in (stats.namespaces or {}).keys()
                if ns and ns != "_user_sessions"
            ]
            if not namespaces:
                namespaces = [""]
            self._ns_cache = (now, namespaces)
            return namespaces
        except Exception as e:
            logger.warning("describe_index_stats failed: %s", e)
            return [""]

    def _namespaces(self) -> list[str]:
        """Backward-compatible: all namespaces (router used in retrieve). """
        return self._all_namespaces()

    def _mode_cfg(self, study_mode: str) -> dict:
        modes = config.raw_config.get("study_modes") or {}
        return dict(modes.get(study_mode) or modes.get("standard") or {})

    def _probe_namespaces(
        self, vector: list[float], all_ns: list[str]
    ) -> dict[str, float]:
        """Cheap top_k=1 probe per namespace for content-aware routing."""
        probe: dict[str, float] = {}
        index = self._ensure_index()
        for ns in all_ns:
            try:
                res = index.query(
                    namespace=ns,
                    vector=vector,
                    top_k=1,
                    include_metadata=False,
                )
                matches = getattr(res, "matches", None) or []
                if matches:
                    probe[ns] = float(getattr(matches[0], "score", None) or 0)
                else:
                    probe[ns] = 0.0
            except Exception as e:
                logger.debug("probe ns=%r failed: %s", ns, e)
                probe[ns] = 0.0
        return probe

    def route_namespaces(
        self,
        query: str,
        *,
        vector: list[float] | None = None,
        skip_probe: bool = False,
    ) -> tuple[list[str], dict[str, Any]]:
        all_ns = self._all_namespaces()
        probe_scores = None
        # Probe when multiple books and not disabled
        use_probe = (
            not skip_probe
            and vector is not None
            and len(all_ns) > 1
            and bool((self.pinecone_cfg.get("router") or {}).get("use_probe", True))
        )
        if use_probe:
            probe_scores = self._probe_namespaces(vector, all_ns)
        result = self.router.route(query, all_ns, probe_scores=probe_scores)
        meta = {
            "strategy": result.strategy,
            "reason": result.reason,
            "scores": result.scores,
            "selected": result.namespaces,
            "total": len(all_ns),
            "probed": bool(probe_scores),
        }
        return result.namespaces, meta

    async def retrieve(
        self, query: str, *, namespaces: list[str] | None = None
    ) -> tuple[str, str, list[dict[str, Any]]]:
        """
        Hybrid retrieve over routed (or given) namespaces.
        Returns (context_for_llm, source_hint, citations[])
        """
        try:
            top_k_ns = int(self.pinecone_cfg.get("top_k_per_namespace", 5))
            top_k_dense = int(self.pinecone_cfg.get("top_k_dense", 16))
            top_k_final = int(
                (config.raw_config.get("reranker") or {}).get("top_k")
                or self.pinecone_cfg.get("top_k_final", 4)
            )
            alpha = float(self.pinecone_cfg.get("hybrid_alpha", 0.65))
            candidate_k = int(
                (config.raw_config.get("reranker") or {}).get("candidate_k")
                or max(top_k_dense, 12)
            )

            vector = embedding_service.embed_query(query)

            route_meta: dict[str, Any] = {}
            if namespaces is None:
                namespaces, route_meta = self.route_namespaces(query, vector=vector)
            if not namespaces:
                return "", "", []

            index = self._ensure_index()
            all_matches: list[dict] = []
            for ns in namespaces:
                try:
                    res = index.query(
                        namespace=ns,
                        vector=vector,
                        top_k=top_k_ns,
                        include_metadata=True,
                    )
                    matches = getattr(res, "matches", None) or []
                    for m in matches:
                        mid = getattr(m, "id", None) or ""
                        meta = dict(getattr(m, "metadata", None) or {})
                        meta["_ns"] = ns
                        score = float(getattr(m, "score", None) or 0)
                        text = meta.get("text") or meta.get("content") or ""
                        all_matches.append(
                            {
                                "id": mid,
                                "score": score,
                                "metadata": meta,
                                "text": text,
                            }
                        )
                except Exception as e:
                    logger.warning("Pinecone query ns=%r failed: %s", ns, e)

            # If routed/probed search was empty, one retry against all namespaces
            if (
                not all_matches
                and route_meta.get("strategy") in ("routed", "probed")
            ):
                logger.info("routed retrieve empty; retrying all namespaces")
                return await self.retrieve(query, namespaces=self._all_namespaces())

            seen = set()
            unique = []
            for m in all_matches:
                key = (m["text"][:160], m["metadata"].get("page"), m["metadata"].get("_ns"))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(m)

            unique.sort(key=lambda x: x["score"], reverse=True)
            pool = unique[: max(top_k_dense, candidate_k)]
            # Stage 1: hybrid dense+BM25 fusion → wide candidate pool
            hybrid_pool = hybrid_rerank(
                query, pool, top_k=min(candidate_k, len(pool) or 1), alpha=alpha
            )
            # Stage 2: cross-encoder / Gemini listwise rerank → final top_k
            ranked = await reranker.rerank(
                query, hybrid_pool, top_k=top_k_final
            )
            if not ranked:
                return "", "", []

            citations: list[dict[str, Any]] = []
            parts: list[str] = []
            source_hint = ""
            for i, match in enumerate(ranked):
                meta = match["metadata"]
                text = match.get("text") or ""
                page = meta.get("page", "N/A")
                book = meta.get("book") or meta.get("source") or meta.get("_ns") or "Source"
                cid = f"c{i + 1}"
                chunk_id = match.get("id") or f"{meta.get('_ns')}:{page}:{i}"
                if i == 0:
                    source_hint = f"{book}, p.{page}"
                excerpt = clean_rag_context(text, max_chars=500)
                citations.append(
                    {
                        "ref": cid,
                        "chunk_id": chunk_id,
                        "book": str(book),
                        "page": page,
                        "score": round(float(match.get("score") or 0), 4),
                        "hybrid_score": round(float(match.get("hybrid_score") or 0), 4),
                        "rerank_score": round(float(match.get("rerank_score") or 0), 4),
                        "excerpt": excerpt[:280],
                        "namespace": meta.get("_ns") or "",
                    }
                )
                parts.append(
                    f"[{cid}] book={book} | page={page} | chunk_id={chunk_id}\n{excerpt}"
                )

            context = clean_rag_context("\n\n---\n\n".join(parts), max_chars=7000)
            # Stash route meta on first citation container via side channel is awkward;
            # attach on a synthetic field by returning via citations list attribute — instead
            # store on service last_route for debugging (optional).
            self._last_route = route_meta
            return context, source_hint, citations
        except Exception as e:
            logger.exception("retrieve failed: %s", e)
            return "", "", []

    async def _retrieve_context(self, query: str) -> tuple[str, str]:
        ctx, hint, _ = await self.retrieve(query)
        return ctx, hint

    def _workspace_focus(self, intent: IntentType, study_mode: str) -> str:
        mode = self._mode_cfg(study_mode)
        mode_focus = mode.get("focus") or ""
        if intent == IntentType.DISEASE:
            base = (
                "Disease focus: definition, key clinical features, red flags, "
                "first-line management from the books only."
            )
        elif intent == IntentType.DRUG:
            base = (
                "Drug focus: indications, dose principles if stated, major side effects, "
                "contraindications from the books only."
            )
        elif intent == IntentType.COMPARISON:
            base = "Comparison focus: similarities, differences, when A vs B — only if textbooks support it."
        elif intent == IntentType.STUDY:
            base = "Study focus: high-yield exam facts only from the books."
        else:
            base = "Answer with high-yield points strictly from textbook context."
        return f"{base}\nStudy mode ({study_mode}): {mode_focus}"

    def _build_prompt(
        self,
        *,
        user_query: str,
        intent: IntentType,
        study_mode: str,
        context: str,
        source_hint: str,
        max_facts: int,
        max_sections: int,
        max_summary: int,
        stricter: bool = False,
    ) -> str:
        extra = ""
        if stricter:
            extra = """
RETRY / STRICT MODE:
- Previous draft failed grounding checks.
- Copy phrases more closely from the [cN] excerpts.
- Do NOT add any fact that is not clearly present in those excerpts.
- Prefer fewer facts over invented ones.
- citations_used must be a subset of the cN ids shown below.
"""
        return f"""
You are Notbook AI — a study companion that answers from uploaded sources.
You only reorganize and present text that appears in the CONTEXT below.
You never invent facts, guidelines, or doses.

{_JSON_SCHEMA_HINT}
{extra}

HARD CAPS FOR THIS RESPONSE:
- summary under {max_summary} characters
- core_facts max {max_facts}
- detail_sections max {max_sections} (use 0 sections if mode forbids them)

WORKSPACE FOCUS:
{self._workspace_focus(intent, study_mode)}

USER QUESTION:
{user_query}

TEXTBOOK CONTEXT (only source of truth; each block has [cN] ids):
{context}

Preferred source_citation if model is unsure: {source_hint or "Excerpt"}
"""

    def _apply_mode_caps(self, validated: dict, mode: dict) -> dict:
        max_facts = int(mode.get("max_facts", 3))
        max_sections = int(mode.get("max_sections", 4))
        max_summary = int(mode.get("max_summary_chars", 280))
        validated["core_facts"] = list(validated.get("core_facts") or [])[:max_facts]
        if max_sections <= 0:
            validated["detail_sections"] = []
        else:
            validated["detail_sections"] = list(
                validated.get("detail_sections") or []
            )[:max_sections]
        if validated.get("summary") and len(validated["summary"]) > max_summary:
            validated["summary"] = (
                validated["summary"][: max_summary - 1].rsplit(" ", 1)[0] + "…"
            )
        return validated

    async def query_medical_knowledge(
        self,
        user_query: str,
        intent: IntentType = IntentType.UNKNOWN,
        study_mode: str = "standard",
        namespaces: list[str] | None = None,
    ) -> dict:
        study_mode = (
            study_mode if study_mode in ("brief", "standard", "exam", "ward") else "standard"
        )
        mode = self._mode_cfg(study_mode)
        faith_on = bool(self.faith_cfg.get("enabled", True))
        ns_key = ",".join(namespaces) if namespaces else "*"
        cache_key = hashlib.sha256(
            f"{self.model_name}|{intent.value}|{study_mode}|{ns_key}|faith{int(faith_on)}|{user_query.strip().lower()}".encode()
        ).hexdigest()
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        context, source_hint, citations = await self.retrieve(
            user_query, namespaces=namespaces
        )
        if not context:
            scope = (
                "the selected source"
                if namespaces
                else "the available sources"
            )
            return {
                "error": (
                    f"I couldn't find this in {scope}. "
                    "Try different wording or pick a different source from the menu."
                )
            }

        max_facts = int(mode.get("max_facts", 3))
        max_sections = int(mode.get("max_sections", 4))
        max_summary = int(mode.get("max_summary_chars", 280))
        max_retries = int(self.faith_cfg.get("max_retries", 1)) if faith_on else 0
        min_claim = float(self.faith_cfg.get("min_claim_score", 0.28))
        min_overall = float(self.faith_cfg.get("min_overall_score", 0.22))
        strict = bool(self.faith_cfg.get("strict", True))

        last_error: dict | None = None
        for attempt in range(max_retries + 1):
            stricter = attempt > 0
            prompt = self._build_prompt(
                user_query=user_query,
                intent=intent,
                study_mode=study_mode,
                context=context,
                source_hint=source_hint,
                max_facts=max_facts,
                max_sections=max_sections,
                max_summary=max_summary,
                stricter=stricter,
            )
            try:
                raw = await self.generate_json(prompt)
                validated = NDMValidator.validate(raw)
                if "error" in validated:
                    last_error = validated
                    continue

                validated["citations"] = citations
                validated["study_mode"] = study_mode
                if getattr(self, "_last_route", None):
                    validated["route"] = {
                        "strategy": self._last_route.get("strategy"),
                        "reason": self._last_route.get("reason"),
                        "selected": self._last_route.get("selected"),
                        "total": self._last_route.get("total"),
                    }
                used = validated.get("citations_used")
                if isinstance(used, list):
                    validated["citations_used"] = [str(x) for x in used]
                if source_hint and (
                    not validated.get("source_citation")
                    or validated["source_citation"] == "Textbook excerpt"
                ):
                    validated["source_citation"] = source_hint

                validated = self._apply_mode_caps(validated, mode)

                if faith_on:
                    gate = apply_faithfulness_gate(
                        validated,
                        citations,
                        min_claim_score=min_claim,
                        min_overall_score=min_overall,
                        strict=strict,
                    )
                    if not gate.ok:
                        last_error = gate.ndm
                        if gate.needs_retry and attempt < max_retries:
                            logger.info(
                                "faithfulness retry attempt=%s reason=%s",
                                attempt + 1,
                                gate.fail_reason,
                            )
                            continue
                        return gate.ndm
                    validated = gate.ndm
                    validated["citations"] = citations  # full list for Cite page
                    validated["study_mode"] = study_mode
                    if getattr(self, "_last_route", None):
                        validated["route"] = {
                            "strategy": self._last_route.get("strategy"),
                            "reason": self._last_route.get("reason"),
                            "selected": self._last_route.get("selected"),
                            "total": self._last_route.get("total"),
                        }
                    validated = self._apply_mode_caps(validated, mode)

                self.cache.set(cache_key, validated)
                return validated
            except Exception as e:
                logger.exception("Gemini generation failed attempt=%s", attempt)
                last_error = {
                    "error": f"Generation failed. Please try again. ({type(e).__name__})"
                }

        return last_error or {
            "error": "Could not produce a grounded answer from the sources."
        }

    async def generate_quiz_item(self, title: str, facts: list[str], summary: str) -> dict:
        stem_bits = [title, summary] + list(facts or [])
        blob = " | ".join(strip_for_quiz_stem(x, 120) for x in stem_bits if x)
        cache_key = "quiz:" + hashlib.sha256(blob.encode()).hexdigest()
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        prompt = f"""
Create ONE medical study multiple-choice question from this material only.
Return JSON only:
{{
  "subject": "clinical specialty (e.g. Anatomy, Cardiology)",
  "topic": "short topic name",
  "difficulty": "Low or Medium or High",
  "question": "short stem",
  "options": ["A ...", "B ...", "C ...", "D ..."],
  "correct_index": 0,
  "explanation": "one short sentence why the correct option is right"
}}
Rules: no markdown, no emoji, exactly 4 options, exactly one correct, short wording.
Only use the material — do not invent clinical guidance.
MATERIAL:
{blob}
"""
        try:
            raw = await self.generate_json(prompt)
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
            if not isinstance(data, dict):
                return {"error": "Quiz parse failed"}
            opts = data.get("options") or []
            if len(opts) < 2:
                return {"error": "Quiz incomplete"}
            data["options"] = [strip_for_quiz_stem(str(o), 100) for o in opts[:4]]
            data["question"] = strip_for_quiz_stem(str(data.get("question") or ""), 180)
            data["explanation"] = strip_for_quiz_stem(str(data.get("explanation") or ""), 200)
            data["subject"] = strip_for_quiz_stem(str(data.get("subject") or ""), 40) or "General"
            data["topic"] = strip_for_quiz_stem(str(data.get("topic") or ""), 60) or title
            data["difficulty"] = strip_for_quiz_stem(str(data.get("difficulty") or ""), 20) or "Medium"
            idx = int(data.get("correct_index", 0))
            data["correct_index"] = max(0, min(idx, len(data["options"]) - 1))
            self.cache.set(cache_key, data)
            return data
        except Exception as e:
            logger.warning("Quiz generation failed: %s", e)
            return {"error": "Could not build a quiz from this topic."}

    async def generate_flashcards(
        self, title: str, facts: list[str], summary: str, sections: list[dict]
    ) -> list[dict]:
        bits = [title, summary] + list(facts or [])
        for s in sections or []:
            if isinstance(s, dict):
                bits.append(f"{s.get('heading')}: {s.get('body')}")
        blob = "\n".join(str(b) for b in bits if b)[:3500]
        prompt = f"""
Create 3 to 5 flashcards for medical study from ONLY this material.
Return JSON: {{"cards": [{{"front": "question", "back": "answer"}}]}}
Rules: short fronts, short backs, no markdown, no emoji, no invented facts.
MATERIAL:
{blob}
"""
        try:
            raw = await self.generate_json(prompt)
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
            cards = data.get("cards") if isinstance(data, dict) else None
            if not isinstance(cards, list):
                return []
            out = []
            for c in cards[:5]:
                if not isinstance(c, dict):
                    continue
                front = strip_for_quiz_stem(str(c.get("front") or ""), 200)
                back = strip_for_quiz_stem(str(c.get("back") or ""), 400)
                if front and back:
                    out.append({"front": front, "back": back})
            return out
        except Exception as e:
            logger.warning("Flashcard gen failed: %s", e)
            out = []
            for f in (facts or [])[:3]:
                out.append({"front": f"Recall: {title}?", "back": str(f)})
            if summary:
                out.append({"front": f"Summarize {title}", "back": summary[:300]})
            return out


gemini_service = GeminiService()
