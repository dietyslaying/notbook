"""Unified embedding client: Gemini (default) or Pinecone Inference.

Query and document paths use the correct task type / e5 prefix so the
same model is used at ingest and retrieve time.

Gemini path uses gemini_key_pool: rotate keys on 429/quota instead of
sticking to one exhausted free-tier key.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from pinecone import Pinecone

from config import config
from services.gemini_key_pool import gemini_key_pool, is_quota_or_rate

logger = logging.getLogger(__name__)

TaskKind = Literal["query", "document"]


class EmbeddingService:
    def __init__(self) -> None:
        emb = config.raw_config.get("embeddings") or {}
        pc_cfg = config.raw_config.get("pinecone") or {}

        self.provider = str(emb.get("provider") or "gemini").lower()
        self.model = str(
            emb.get("model")
            or (
                "gemini-embedding-001"
                if self.provider == "gemini"
                else pc_cfg.get("embedding_model") or "multilingual-e5-large"
            )
        )
        self.dimension = int(
            emb.get("dimension") or pc_cfg.get("dimension") or 768
        )
        self.batch_size = int(emb.get("batch_size") or 24)

        # Pinecone path still needs the client for pinecone provider
        self._pc = Pinecone(api_key=config.pinecone_api_key)

    def embed_texts(
        self,
        texts: list[str],
        *,
        task: TaskKind = "document",
        max_retries: int = 8,
    ) -> list[list[float]]:
        if not texts:
            return []
        if self.provider == "pinecone":
            return self._embed_pinecone(texts, task=task, max_retries=max_retries)
        return self._embed_gemini(texts, task=task, max_retries=max_retries)

    def embed_query(self, query: str) -> list[float]:
        vecs = self.embed_texts([query], task="query")
        return vecs[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_texts(texts, task="document")

    def _embed_one_batch(
        self,
        client,
        batch: list[str],
        *,
        task_type: str,
        allow_single_fallback: bool,
    ) -> list[list[float]]:
        """Embed one batch; optionally fall back to per-item (never on 429)."""
        from google.genai import types

        try:
            result = client.models.embed_content(
                model=self.model,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.dimension,
                ),
            )
            embeddings = getattr(result, "embeddings", None) or []
            if len(embeddings) == len(batch):
                return [
                    list(getattr(emb, "values", None) or []) for emb in embeddings
                ]
            raise RuntimeError(
                f"Batch embed size mismatch: got {len(embeddings)} want {len(batch)}"
            )
        except Exception as e:
            err = str(e)
            # Never explode into N single calls when rate-limited — that burns quota
            if is_quota_or_rate(err) or not allow_single_fallback:
                raise
            # Non-quota batch API failure → try one-by-one with SAME client once
            logger.warning(
                "Gemini batch embed failed (non-quota), trying per-item: %s",
                err[:160],
            )
            chunk_vecs: list[list[float]] = []
            for text in batch:
                result = client.models.embed_content(
                    model=self.model,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=self.dimension,
                    ),
                )
                emb = None
                if getattr(result, "embeddings", None):
                    emb = result.embeddings[0]
                elif getattr(result, "embedding", None):
                    emb = result.embedding
                if emb is None:
                    raise RuntimeError("No embedding in Gemini response")
                chunk_vecs.append(list(getattr(emb, "values", None) or []))
            return chunk_vecs

    def _embed_gemini(
        self,
        texts: list[str],
        *,
        task: TaskKind,
        max_retries: int,
    ) -> list[list[float]]:
        task_type = (
            "RETRIEVAL_QUERY" if task == "query" else "RETRIEVAL_DOCUMENT"
        )
        n_keys = max(1, gemini_key_pool.key_count())
        # Give every key a couple of tries across the pool
        attempts_cap = max(max_retries, n_keys * 3)
        out: list[list[float]] = []

        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            last_err: Exception | None = None
            done = False

            for attempt in range(attempts_cap):
                api_key, client = gemini_key_pool.acquire()
                try:
                    vecs = self._embed_one_batch(
                        client,
                        batch,
                        task_type=task_type,
                        allow_single_fallback=True,
                    )
                    gemini_key_pool.mark_ok(api_key)
                    out.extend(vecs)
                    done = True
                    break
                except Exception as e:
                    last_err = e
                    err = str(e)
                    cool = gemini_key_pool.mark_error(api_key, e)
                    if is_quota_or_rate(err):
                        # Rotate immediately — only pause hard if a single key exists
                        logger.warning(
                            "Embed 429/quota on key (attempt %s/%s); "
                            "rotating to next key (cooldown %.0fs on this one)",
                            attempt + 1,
                            attempts_cap,
                            cool,
                        )
                        if n_keys <= 1:
                            time.sleep(min(cool, 15.0))
                        continue
                    # non-quota: short backoff then try other keys
                    time.sleep(min(2.0 * (attempt + 1), 10.0))

            if not done:
                st = gemini_key_pool.status()
                raise RuntimeError(
                    f"Gemini embed failed after rotating across {st['total']} key(s) "
                    f"({st['ready']} ready). Last error: {last_err}"
                ) from last_err

        if len(out) != len(texts):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(out)} for {len(texts)} texts"
            )
        return out

    def _embed_pinecone(
        self,
        texts: list[str],
        *,
        task: TaskKind,
        max_retries: int,
    ) -> list[list[float]]:
        # e5-style prefix
        prefix = "query: " if task == "query" else "passage: "
        inputs = [f"{prefix}{t}" for t in texts]
        out: list[list[float]] = []
        for start in range(0, len(inputs), self.batch_size):
            batch = inputs[start : start + self.batch_size]
            for attempt in range(max_retries):
                try:
                    resp = self._pc.inference.embed(
                        model=self.model,
                        inputs=batch,
                        parameters={
                            "input_type": "query" if task == "query" else "passage",
                            "truncate": "END",
                        },
                    )
                    data = getattr(resp, "data", None) or resp
                    for item in data:
                        vals = getattr(item, "values", None) or item["values"]
                        out.append(list(vals))
                    break
                except Exception as e:
                    err = str(e)
                    if "429" in err or "RESOURCE_EXHAUSTED" in err or "RateLimit" in err:
                        wait = 30 * (attempt + 1)
                        logger.warning("Pinecone embed rate limited, sleep %ss", wait)
                        time.sleep(wait)
                    else:
                        raise
            else:
                raise RuntimeError("Pinecone embed retries exceeded")
        return out


embedding_service = EmbeddingService()
