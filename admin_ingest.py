import os
import re
import time
import argparse
import yaml
import logging
import pypdfium2 as pdfium
from pinecone import Pinecone, ServerlessSpec

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY environment variable is missing")

pc = Pinecone(api_key=PINECONE_API_KEY)
index_name = config['pinecone']['index_name']


# ---------------------------------------------------------------------------
# Pinecone index setup
# ---------------------------------------------------------------------------

def init_pinecone():
    """Ensures the Pinecone index exists with the correct dimension."""
    try:
        idx_info = pc.describe_index(index_name)
        if idx_info.dimension != 1024:
            logger.info(f"Deleting incompatible index (wrong dimension): {index_name}")
            pc.delete_index(index_name)
            time.sleep(5)
    except Exception:
        pass

    if index_name not in pc.list_indexes().names():
        logger.info(f"Creating Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=1024,
            metric='cosine',
            spec=ServerlessSpec(cloud='aws', region='us-east-1')
        )
        # Wait for index to be ready
        while True:
            status = pc.describe_index(index_name).status
            if status.get("ready", False):
                break
            logger.info("Waiting for index to become ready...")
            time.sleep(3)

    return pc.Index(index_name)


def delete_namespace(index, namespace: str):
    """Deletes all vectors in a namespace (i.e. removes a book)."""
    logger.info(f"Deleting all vectors in namespace '{namespace}'...")
    try:
        index.delete(delete_all=True, namespace=namespace)
        logger.info("Namespace cleared.")
    except Exception as e:
        logger.warning(f"Could not clear namespace (may already be empty): {e}")


# ---------------------------------------------------------------------------
# Smart text extraction (page-by-page with metadata)
# ---------------------------------------------------------------------------

def is_garbage_page(text: str) -> bool:
    """
    Returns True for pages that are index pages, abbreviation lists, or
    reference-only pages — content that pollutes RAG results.

    Heuristics:
      - Very short pages (< 100 chars of real content)
      - >60% of non-empty lines are very short (< 30 chars) — typical of indexes
      - >40% of lines end with a page number pattern (e.g. "....... 432")
    """
    text = text.strip()
    if len(text) < 100:
        return True

    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return True

    short_lines = sum(1 for l in lines if len(l.strip()) < 35)
    dotted_lines = sum(1 for l in lines if re.search(r'[\.\s]{4,}\d+\s*$', l))

    if len(lines) > 5 and short_lines / len(lines) > 0.65:
        return True   # index / abbreviation page
    if len(lines) > 5 and dotted_lines / len(lines) > 0.40:
        return True   # table-of-contents / index page

    return False


def extract_pages(pdf_path: str) -> list[dict]:
    """
    Extracts text from every page, returning a list of
    {'page': int, 'text': str} dicts, skipping garbage pages.
    """
    doc = pdfium.PdfDocument(pdf_path)
    pages = []
    skipped = 0
    for page_num, page in enumerate(doc, start=1):
        textpage = page.get_textpage()
        text = textpage.get_text_range()
        if not text:
            skipped += 1
            continue
        # Normalise whitespace
        text = re.sub(r'\r\n|\r', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        if is_garbage_page(text):
            skipped += 1
            continue
        pages.append({'page': page_num, 'text': text})

    logger.info(f"Extracted {len(pages)} content pages, skipped {skipped} garbage/blank pages.")
    return pages


# ---------------------------------------------------------------------------
# Smart chunking (paragraph-first, then sentence, then character)
# ---------------------------------------------------------------------------

def split_into_chunks(pages: list[dict], max_chars: int = 600, overlap: int = 80) -> list[dict]:
    """
    Splits page text into chunks. Strategy (in priority order):
      1. Split on double-newline (paragraph boundary)
      2. If a paragraph is still too long, split on sentence endings
      3. If a sentence is still too long, hard-split by character count

    Each chunk carries its source page number.
    """
    chunks = []

    for page_data in pages:
        page_num = page_data['page']
        page_text = page_data['text']

        # First split into paragraphs
        paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]

        pending = ""
        for para in paragraphs:
            # If adding this paragraph keeps us under the limit, accumulate
            if len(pending) + len(para) + 2 <= max_chars:
                pending = (pending + "\n\n" + para).strip()
            else:
                # Flush pending as a chunk
                if pending:
                    chunks.append({'text': pending, 'page': page_num})
                    # Overlap: keep last `overlap` chars as context seed
                    pending = pending[-overlap:].strip()

                # If paragraph itself is too big, split it further at sentences
                if len(para) > max_chars:
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    for sentence in sentences:
                        if len(pending) + len(sentence) + 1 <= max_chars:
                            pending = (pending + " " + sentence).strip()
                        else:
                            if pending:
                                chunks.append({'text': pending, 'page': page_num})
                                pending = pending[-overlap:].strip()
                            # Sentence is still too long: hard-split by chars
                            while len(sentence) > max_chars:
                                chunks.append({'text': sentence[:max_chars], 'page': page_num})
                                sentence = sentence[max_chars - overlap:]
                            pending = sentence
                else:
                    pending = para

        if pending:
            chunks.append({'text': pending, 'page': page_num})

    # Final quality filter: drop chunks that are too short to be useful
    chunks = [c for c in chunks if len(c['text'].strip()) >= 80]
    return chunks


# ---------------------------------------------------------------------------
# Embedding + upsert with retry
# ---------------------------------------------------------------------------

def embed_with_retry(texts: list[str], max_retries: int = 5) -> list:
    """Calls Pinecone inference embed with exponential backoff on rate limits."""
    for attempt in range(max_retries):
        try:
            response = pc.inference.embed(
                model=config['pinecone']['embedding_model'],
                inputs=texts,
                parameters={"input_type": "passage", "truncate": "END"}
            )
            return response
        except Exception as e:
            err = str(e)
            if '429' in err or 'RESOURCE_EXHAUSTED' in err or 'RateLimitError' in err:
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s …
                logger.warning(f"Rate limited. Sleeping {wait}s (attempt {attempt+1}/{max_retries})…")
                time.sleep(wait)
            else:
                raise e
    raise RuntimeError("Exceeded max retries on Pinecone rate limit.")


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def ingest_pdf(pdf_path: str, namespace: str, user_id: str = None):
    index = init_pinecone()
    
    target_namespace = f"{user_id}|{namespace}" if user_id else f"global|{namespace}"

    # 1. Wipe the existing namespace so we start fresh
    delete_namespace(index, target_namespace)

    # 2. Extract pages (skipping indexes, abbreviations, etc.)
    logger.info(f"Reading PDF: {pdf_path}")
    pages = extract_pages(pdf_path)

    # 3. Smart chunking
    chunks = split_into_chunks(pages, max_chars=600, overlap=80)
    logger.info(f"Created {len(chunks)} clean chunks.")

    # 4. Embed and upsert in batches of 96
    batch_size = 96
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c['text'] for c in batch]
        batch_num = i // batch_size + 1
        logger.info(f"Embedding batch {batch_num}/{total_batches} ({len(texts)} chunks)…")

        embeddings = embed_with_retry(texts)

        vectors = []
        for j, embedding in enumerate(embeddings):
            chunk_idx = i + j
            metadata = {
                "text": batch[j]['text'],
                "page": batch[j]['page'],
                "source": os.path.basename(pdf_path)
            }
                
            vectors.append({
                "id": f"chunk_{chunk_idx}",
                "values": embedding.values,
                "metadata": metadata
            })

        index.upsert(vectors=vectors, namespace=target_namespace)

    logger.info(f"\n✅ Successfully ingested '{os.path.basename(pdf_path)}' "
                f"({len(chunks)} chunks) into namespace '{target_namespace}'.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest a PDF into Pinecone for RAG.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("book_name", help="Name of the book (used as the Pinecone namespace)")
    parser.add_argument("--user_id", help="Telegram User ID to restrict access to", default=None)
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        logger.error(f"File not found: {args.pdf_path}")
        exit(1)

    ingest_pdf(args.pdf_path, args.book_name, args.user_id)
