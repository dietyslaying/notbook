"""Legacy: smoke test. Uses env vars + dotenv only."""

from __future__ import annotations

import asyncio
import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


async def main() -> None:
    if not os.getenv("PINECONE_API_KEY"):
        print("PINECONE_API_KEY missing", file=sys.stderr)
        sys.exit(1)

    try:
        sys.path.insert(0, os.path.abspath("notbook_ai"))
        from services.gemini_service import gemini_service

        query = os.getenv("TEST_QUERY", "Tell me about asthma")
        print("Using notbook_ai gemini_service.retrieve…")
        ctx, hint, cites = await gemini_service.retrieve(query)
        print("hint:", hint)
        print("citations:", len(cites))
        print("context sample:", (ctx or "")[:300])
    except Exception as e:
        print("Active service path failed:", e)
        print("Fall back: run test_pinecone_sync.py with Pinecone inference.")


if __name__ == "__main__":
    asyncio.run(main())
