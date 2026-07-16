"""Legacy helper: print Pinecone stats + optional local PDF page counts.

Requires env:
  PINECONE_API_KEY
Optional:
  PINECONE_INDEX — default library-index-v2
  PDF_PATH — absolute path to a PDF to inspect
"""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from pinecone import Pinecone


def main() -> None:
    key = os.getenv("PINECONE_API_KEY")
    if not key:
        print("PINECONE_API_KEY not set in environment / .env", file=sys.stderr)
        sys.exit(1)

    index_name = os.getenv("PINECONE_INDEX", "library-index-v2")
    pc = Pinecone(api_key=key)
    index = pc.Index(index_name)
    stats = index.describe_index_stats()

    print("=== PINECONE INDEX STATS ===")
    total = getattr(stats, "total_vector_count", None)
    if total is None and isinstance(stats, dict):
        total = stats.get("total_vector_count")
    print(f"Index: {index_name}")
    print(f"Total vectors: {total}")
    namespaces = getattr(stats, "namespaces", None)
    if namespaces is None and isinstance(stats, dict):
        namespaces = stats.get("namespaces") or {}
    for ns, data in (namespaces or {}).items():
        count = getattr(data, "vector_count", None)
        if count is None and isinstance(data, dict):
            count = data.get("vector_count")
        print(f'  Namespace "{ns}": {count} vectors')

    pdf_path = os.getenv("PDF_PATH", "").strip()
    if not pdf_path:
        print("\n(Set PDF_PATH to inspect a local PDF page count.)")
        return

    try:
        import pypdfium2 as pdfium
    except ImportError:
        print("pypdfium2 not installed; skip PDF inspection", file=sys.stderr)
        return

    if not os.path.isfile(pdf_path):
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print("\n=== PDF PAGE COUNT ===")
    doc = pdfium.PdfDocument(pdf_path)
    total_pages = len(doc)
    print(f"Total pages in PDF: {total_pages}")
    non_empty = 0
    for page in doc:
        tp = page.get_textpage()
        if tp.get_text_range().strip():
            non_empty += 1
    print(f"Non-empty pages: {non_empty}")
    print(f"Blank/image-only pages: {total_pages - non_empty}")


if __name__ == "__main__":
    main()
