"""Admin PDF ingest into Pinecone (chunk → embed → upsert) with stable chunk IDs."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional

from pinecone import Pinecone, ServerlessSpec

from config import config
from services.embeddings import embedding_service
from services.gemini_key_pool import gemini_key_pool

logger = logging.getLogger(__name__)

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover
    pdfium = None


def is_garbage_page(text: str) -> bool:
    text = text.strip()
    if len(text) < 100:
        return True
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return True
    short_lines = sum(1 for l in lines if len(l.strip()) < 35)
    dotted_lines = sum(1 for l in lines if re.search(r"[\.\s]{4,}\d+\s*$", l))
    if len(lines) > 5 and short_lines / len(lines) > 0.65:
        return True
    if len(lines) > 5 and dotted_lines / len(lines) > 0.40:
        return True
    return False


def extract_pages(pdf_path: str) -> list[dict]:
    if pdfium is None:
        raise RuntimeError("pypdfium2 is required for PDF ingest. pip install pypdfium2")
    doc = pdfium.PdfDocument(pdf_path)
    pages = []
    skipped = 0
    for page_num, page in enumerate(doc, start=1):
        textpage = page.get_textpage()
        text = textpage.get_text_range() or ""
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text or is_garbage_page(text):
            skipped += 1
            continue
        pages.append({"page": page_num, "text": text})
    logger.info("Extracted %s pages, skipped %s", len(pages), skipped)
    return pages


def split_into_chunks(
    pages: list[dict], max_chars: int = 600, overlap: int = 80
) -> list[dict]:
    chunks: list[dict] = []
    for page_data in pages:
        page_num = page_data["page"]
        paragraphs = [p.strip() for p in page_data["text"].split("\n\n") if p.strip()]
        pending = ""
        for para in paragraphs:
            if len(pending) + len(para) + 2 <= max_chars:
                pending = (pending + "\n\n" + para).strip()
            else:
                if pending:
                    chunks.append({"text": pending, "page": page_num})
                    pending = pending[-overlap:].strip()
                if len(para) > max_chars:
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    for sentence in sentences:
                        if len(pending) + len(sentence) + 1 <= max_chars:
                            pending = (pending + " " + sentence).strip()
                        else:
                            if pending:
                                chunks.append({"text": pending, "page": page_num})
                                pending = pending[-overlap:].strip()
                            while len(sentence) > max_chars:
                                chunks.append(
                                    {"text": sentence[:max_chars], "page": page_num}
                                )
                                sentence = sentence[max_chars - overlap :]
                            pending = sentence
                else:
                    pending = para
        if pending:
            chunks.append({"text": pending, "page": page_num})
    return [c for c in chunks if len(c["text"].strip()) >= 80]


class IngestService:
    def __init__(self) -> None:
        self.pc = Pinecone(api_key=config.pinecone_api_key)
        self.cfg = config.raw_config.get("pinecone") or {}
        self.ingest_cfg = config.raw_config.get("ingest") or {}
        self.index_name = self.cfg.get("index_name", "library-index-v2")
        self.dimension = int(
            self.cfg.get("dimension")
            or (config.raw_config.get("embeddings") or {}).get("dimension")
            or embedding_service.dimension
        )

    def _ensure_index(self):
        names = list(self.pc.list_indexes().names())
        if self.index_name in names:
            info = self.pc.describe_index(self.index_name)
            existing_dim = getattr(info, "dimension", None)
            if existing_dim is not None and int(existing_dim) != int(self.dimension):
                raise RuntimeError(
                    f"Pinecone index '{self.index_name}' is {existing_dim}-d but "
                    f"config wants {self.dimension}-d. "
                    f"Either delete the index, or set pinecone.index_name to a new "
                    f"name (e.g. library-index-v2), then re-ingest all PDFs."
                )
        else:
            logger.info(
                "Creating Pinecone index %s dim=%s", self.index_name, self.dimension
            )
            self.pc.create_index(
                name=self.index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            for _ in range(40):
                if self.pc.describe_index(self.index_name).status.get("ready"):
                    break
                time.sleep(2)
        return self.pc.Index(self.index_name)

    def ingest_pdf(
        self,
        pdf_path: str,
        book_name: str,
        *,
        progress: Optional[Callable[..., None]] = None,
        wipe_namespace: bool = True,
    ) -> dict:
        """
        progress callback receives either a str (legacy) or a dict:
          {msg, phase, pct, current, total, ts}
        """

        def report(
            msg: str,
            *,
            phase: str = "",
            pct: Optional[float] = None,
            current: Optional[int] = None,
            total: Optional[int] = None,
        ) -> None:
            logger.info(msg)
            if not progress:
                return
            event = {
                "msg": msg,
                "phase": phase or "",
                "pct": pct,
                "current": current,
                "total": total,
                "ts": time.time(),
            }
            try:
                progress(event)
            except TypeError:
                # Older callers: progress(str)
                progress(msg)

        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(pdf_path)

        safe_book = re.sub(r"[^\w\s\-\.]+", "", book_name).strip() or path.stem
        namespace = f"global|{safe_book}"

        report("Ensuring Pinecone index…", phase="init", pct=2)
        index = self._ensure_index()
        report(
            f"Index ready: {self.index_name} (dim={self.dimension})",
            phase="init",
            pct=5,
        )

        if wipe_namespace:
            try:
                report(f"Clearing namespace {namespace}…", phase="clear", pct=8)
                index.delete(delete_all=True, namespace=namespace)
                report(f"Cleared namespace {namespace}", phase="clear", pct=12)
            except Exception as e:
                report(f"Namespace clear skipped: {e}", phase="clear", pct=12)

        report(
            f"Reading {path.name}… (embed={embedding_service.provider}/"
            f"{embedding_service.model} dim={self.dimension}"
            + (
                f" · gemini_keys={gemini_key_pool.key_count()}"
                if embedding_service.provider == "gemini"
                else ""
            )
            + ")",
            phase="read",
            pct=15,
        )
        pages = extract_pages(str(path))
        report(
            f"Extracted {len(pages)} content pages",
            phase="read",
            pct=22,
            current=len(pages),
            total=len(pages),
        )

        max_chars = int(self.ingest_cfg.get("chunk_max_chars", 600))
        overlap = int(self.ingest_cfg.get("chunk_overlap", 80))
        batch_size = int(self.ingest_cfg.get("batch_size", 24))
        report("Chunking text…", phase="chunk", pct=25)
        chunks = split_into_chunks(pages, max_chars=max_chars, overlap=overlap)
        n_chunks = len(chunks)
        report(
            f"{n_chunks} chunks from {len(pages)} pages "
            f"(batch_size={batch_size})",
            phase="chunk",
            pct=30,
            current=0,
            total=n_chunks,
        )

        if n_chunks == 0:
            raise RuntimeError("No chunks produced from PDF (all pages filtered?)")

        total = 0
        n_batches = (n_chunks + batch_size - 1) // batch_size
        for bi, i in enumerate(range(0, n_chunks, batch_size)):
            batch = chunks[i : i + batch_size]
            texts = [c["text"] for c in batch]
            # Map embed+upsert into 30% → 98%
            base_pct = 30 + (bi / max(n_batches, 1)) * 68
            report(
                f"Embedding batch {bi + 1}/{n_batches} "
                f"({len(texts)} chunks)…",
                phase="embed",
                pct=round(base_pct, 1),
                current=total,
                total=n_chunks,
            )
            vectors_emb = embedding_service.embed_documents(texts)
            vectors = []
            for j, values in enumerate(vectors_emb):
                chunk_idx = i + j
                chunk_id = f"{safe_book}::p{batch[j]['page']}::c{chunk_idx}"
                vectors.append(
                    {
                        "id": chunk_id,
                        "values": values,
                        "metadata": {
                            "text": batch[j]["text"][:3500],
                            "page": batch[j]["page"],
                            "book": safe_book,
                            "source": path.name,
                            "chunk_index": chunk_idx,
                            "embed_model": embedding_service.model,
                            "embed_provider": embedding_service.provider,
                        },
                    }
                )
            report(
                f"Upserting batch {bi + 1}/{n_batches}…",
                phase="upsert",
                pct=round(base_pct + (68 / max(n_batches, 1)) * 0.6, 1),
                current=total,
                total=n_chunks,
            )
            index.upsert(vectors=vectors, namespace=namespace)
            total += len(vectors)
            done_pct = 30 + (total / n_chunks) * 68
            report(
                f"Upserted {total}/{n_chunks} chunks "
                f"({100 * total / n_chunks:.0f}%)",
                phase="upsert",
                pct=round(min(98.0, done_pct), 1),
                current=total,
                total=n_chunks,
            )

        report(
            f"Done: {safe_book} → {namespace} ({total} chunks)",
            phase="done",
            pct=100,
            current=total,
            total=total,
        )
        return {
            "namespace": namespace,
            "book": safe_book,
            "chunks": total,
            "pages": len(pages),
            "embed_model": embedding_service.model,
            "dimension": self.dimension,
            "index": self.index_name,
        }


ingest_service = IngestService()
