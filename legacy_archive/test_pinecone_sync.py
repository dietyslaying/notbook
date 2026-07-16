"""Legacy: smoke-test Pinecone embed + query. Uses env vars only."""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import yaml
from pinecone import Pinecone


def main() -> None:
    key = os.getenv("PINECONE_API_KEY")
    if not key:
        print("PINECONE_API_KEY missing", file=sys.stderr)
        sys.exit(1)

    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    pc_cfg = config.get("pinecone") or {}
    index_name = pc_cfg.get("index_name") or os.getenv(
        "PINECONE_INDEX", "library-index-v2"
    )
    emb_model = pc_cfg.get("embedding_model") or "multilingual-e5-large"
    namespace = os.getenv("PINECONE_NAMESPACE", "global|murtaghs")
    query = os.getenv("TEST_QUERY", "asthma")

    pc = Pinecone(api_key=key)
    index = pc.Index(index_name)

    print("Embedding query...")
    query_embedding = pc.inference.embed(
        model=emb_model,
        inputs=[f"query: {query}"],
        parameters={"input_type": "query", "truncate": "END"},
    )
    values = query_embedding.data[0].values

    print(f"Searching Pinecone index={index_name} ns={namespace!r}...")
    search_results = index.query(
        namespace=namespace,
        vector=values,
        top_k=12,
        include_metadata=True,
    )
    matches = getattr(search_results, "matches", None) or []
    print(f"Total matches found: {len(matches)}")
    for i, m in enumerate(matches):
        meta = getattr(m, "metadata", None) or {}
        print(f"Match {i + 1}: Score = {m.score}, Page = {meta.get('page')}")
        print(f"Text snippet: {str(meta.get('text', ''))[:100]}...")


if __name__ == "__main__":
    main()
