"""Unified embedding client: Gemini (default) or Pinecone Inference.

Query and document paths use the correct task type / e5 prefix so the
same model is used at ingest and retrieve time.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Literal

from pinecone import Pinecone

from config import config

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
        self.batch_size = int(emb.get("batch_size") or 32)

        # Pinecone path still needs the client for pinecone provider
        self._pc = Pinecone(api_key=config.pinecone_api_key)
        self._gemini_clients: dict = {}

    def _gemini_client(self):
        from google import genai

        keys = config.gemini_api_keys
        if not keys:
            raise RuntimeError("GEMINI_API_KEY required for Gemini embeddings")
        key = random.choice(keys)
        if key not in self._gemini_clients:
            self._gemini_clients[key] = genai.Client(api_key=key)
        return self._gemini_clients[key]

    def embed_texts(
        self,
        texts: list[str],
        *,
        task: TaskKind = "document",
        max_retries: int = 5,
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

    def _embed_gemini(
        self,
        texts: list[str],
        *,
        task: TaskKind,
        max_retries: int,
    ) -> list[list[float]]:
        from google.genai import types

        client = self._gemini_client()
        task_type = (
            "RETRIEVAL_QUERY" if task == "query" else "RETRIEVAL_DOCUMENT"
        )
        out: list[list[float]] = []

        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            last_err: Exception | None = None
            for attempt in range(max_retries):
                try:
                    # Prefer batch embed; fall back to one-by-one if needed
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
                            for emb in embeddings:
                                vals = list(getattr(emb, "values", None) or [])
                                out.append(vals)
                            break
                    except Exception:
                        # Per-item (safer for some embedding-2 builds)
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
                        out.extend(chunk_vecs)
                        break
                except Exception as e:
                    last_err = e
                    err = str(e)
                    if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                        wait = 20 * (attempt + 1)
                        logger.warning("Gemini embed rate limited, sleep %ss", wait)
                        time.sleep(wait)
                    else:
                        if attempt + 1 >= max_retries:
                            raise
                        time.sleep(2 * (attempt + 1))
            else:
                if last_err:
                    raise last_err

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
