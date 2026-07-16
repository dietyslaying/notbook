"""
RAG / answer eval harness for Notbook.

Usage (from project root):
  python evals/run_eval.py
  python evals/run_eval.py --limit 3
  python evals/run_eval.py --retrieval-only

Scores:
  - retrieval_hit: any gold keyword appears in retrieved context
  - answer_hit: any gold keyword appears in final answer fields
  - fail_closed: expect_no_answer cases correctly error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "notbook_ai")]


async def run(limit: int | None, retrieval_only: bool) -> int:
    from services.gemini_service import gemini_service
    from interfaces import IntentType

    gold_path = Path(__file__).parent / "gold_set.json"
    cases = json.loads(gold_path.read_text(encoding="utf-8"))
    if limit:
        cases = cases[:limit]

    results = []
    for case in cases:
        q = case["query"]
        cid = case["id"]
        print(f"\n=== {cid} ===\nQ: {q}")

        context, hint, citations = await gemini_service.retrieve(q)
        ctx_l = (context or "").lower()
        keys = [k.lower() for k in case.get("must_include_any") or []]

        retrieval_hit = None
        if keys:
            retrieval_hit = any(k in ctx_l for k in keys)
            print(f"retrieval_hit={retrieval_hit} citations={len(citations)} hint={hint!r}")
        elif case.get("expect_no_answer"):
            retrieval_hit = not bool(context.strip())
            print(f"empty_retrieval_ok={retrieval_hit}")

        answer_hit = None
        err = None
        if not retrieval_only and not case.get("expect_no_answer"):
            ndm = await gemini_service.query_medical_knowledge(
                q, intent=IntentType.UNKNOWN, study_mode="standard"
            )
            if "error" in ndm:
                err = ndm["error"]
                answer_hit = False
                print(f"answer ERROR: {err}")
            else:
                blob = " ".join(
                    [
                        str(ndm.get("title") or ""),
                        str(ndm.get("summary") or ""),
                        " ".join(ndm.get("core_facts") or []),
                        str(ndm.get("source_citation") or ""),
                    ]
                ).lower()
                answer_hit = any(k in blob for k in keys) if keys else True
                print(f"answer_hit={answer_hit} title={ndm.get('title')!r}")
        elif case.get("expect_no_answer") and not retrieval_only:
            ndm = await gemini_service.query_medical_knowledge(q)
            fail_closed = "error" in ndm
            print(f"fail_closed={fail_closed}")
            results.append(
                {
                    "id": cid,
                    "retrieval_hit": retrieval_hit,
                    "fail_closed": fail_closed,
                    "ok": bool(fail_closed),
                }
            )
            continue

        ok = True
        if retrieval_hit is False:
            ok = False
        if answer_hit is False:
            ok = False
        results.append(
            {
                "id": cid,
                "retrieval_hit": retrieval_hit,
                "answer_hit": answer_hit,
                "citations": len(citations),
                "ok": ok,
            }
        )

    passed = sum(1 for r in results if r.get("ok"))
    print(f"\n==== SUMMARY {passed}/{len(results)} passed ====")
    out = Path(__file__).parent / "last_results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0 if passed == len(results) else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retrieval-only", action="store_true")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.limit, args.retrieval_only)))


if __name__ == "__main__":
    main()
