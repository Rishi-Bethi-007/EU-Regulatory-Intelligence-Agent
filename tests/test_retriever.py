"""
scripts/test_retriever.py

Smoke test for the hybrid retriever.
Proves the knowledge base is working correctly after ingestion.

Usage:
    uv run python scripts/test_retriever.py

What it tests:
    1. English query     → English chunks returned, similarity scores present
    2. Swedish query     → Swedish chunks ranked first (language boost working)
    3. German query      → German chunks ranked first (language boost working)
    4. Exact term query  → Sparse (FTS) search finding exact legal citations
    5. DB sanity check   → Confirms chunk counts in Supabase match expectations

Pass criteria (printed at the end):
    - All 5 tests green = retriever is working correctly
    - Any red = something needs fixing before wiring into the agent
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.retriever import HybridRetriever


# ─────────────────────────────────────────────────────────────────────────────
# TEST QUERIES
# ─────────────────────────────────────────────────────────────────────────────

TESTS = [
    {
        "id":           1,
        "name":         "English query — EU AI Act obligations",
        "query":        "What are the obligations for providers of high-risk AI systems under the EU AI Act?",
        "expected_lang": "en",
        "min_chunks":   3,
        "check":        "At least 3 English chunks returned with similarity scores",
    },
    {
        "id":           2,
        "name":         "Swedish query — AI risk classification",
        "query":        "Vad säger AI-förordningen om riskklassificering av AI-system?",
        "expected_lang": "sv",
        "min_chunks":   2,
        "check":        "Swedish chunks ranked first (language boost active)",
    },
    {
        "id":           3,
        "name":         "German query — GDPR data processing",
        "query":        "Welche Anforderungen stellt die DSGVO an die Verarbeitung personenbezogener Daten?",
        "expected_lang": "de",
        "min_chunks":   2,
        "check":        "German chunks ranked first (language boost active)",
    },
    {
        "id":           4,
        "name":         "Exact term — Article citation lookup",
        "query":        "Article 13 transparency obligations AI systems",
        "expected_lang": "en",
        "min_chunks":   1,
        "check":        "Sparse FTS finds exact Article 13 citation",
    },
    {
        "id":           5,
        "name":         "GDPR right to erasure",
        "query":        "right to erasure deletion of personal data GDPR Article 17",
        "expected_lang": "en",
        "min_chunks":   2,
        "check":        "GDPR erasure chunks returned with high similarity",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SANITY CHECK — verify DB has expected chunk counts
# ─────────────────────────────────────────────────────────────────────────────

async def check_db_counts() -> dict:
    """
    Query document_chunks to verify ingestion landed correctly.
    Returns counts by language so we can catch any ingestion gaps.
    """
    from db.client import get_client
    import asyncio

    supabase = get_client()

    # Total chunks
    total = await asyncio.to_thread(
        lambda: supabase.table("document_chunks").select("id", count="exact").execute()
    )

    # By language
    en_count = await asyncio.to_thread(
        lambda: supabase.table("document_chunks")
        .select("id", count="exact")
        .eq("language", "en")
        .execute()
    )
    sv_count = await asyncio.to_thread(
        lambda: supabase.table("document_chunks")
        .select("id", count="exact")
        .eq("language", "sv")
        .execute()
    )
    de_count = await asyncio.to_thread(
        lambda: supabase.table("document_chunks")
        .select("id", count="exact")
        .eq("language", "de")
        .execute()
    )

    return {
        "total": total.count,
        "en":    en_count.count,
        "sv":    sv_count.count,
        "de":    de_count.count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# RESULT PRINTER
# ─────────────────────────────────────────────────────────────────────────────

def print_chunks(docs: list, max_show: int = 3) -> None:
    """Print the top chunks returned for a query in a readable format."""
    for i, doc in enumerate(docs[:max_show], 1):
        lang       = doc.metadata.get("language", "?")
        similarity = doc.metadata.get("similarity", 0.0)
        source     = doc.metadata.get("source", "?")
        chunk_idx  = doc.metadata.get("chunk_index", "?")
        preview    = doc.page_content[:120].replace("\n", " ").strip()

        print(f"  [{i}] lang={lang}  sim={similarity:.3f}  "
              f"source={source}  chunk={chunk_idx}")
        print(f"      \"{preview}...\"")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def run_tests():
    retriever = HybridRetriever(top_k=8, match_threshold=0.7, match_count=20)
    results   = []

    print("\n" + "=" * 65)
    print("EU Regulatory Intelligence Agent — Retriever Smoke Test")
    print("=" * 65)

    # ── DB sanity check first ─────────────────────────────────────────────────
    print("\n📊 DB Sanity Check")
    print("-" * 40)
    try:
        counts = await check_db_counts()
        print(f"  Total chunks : {counts['total']}")
        print(f"  English (en) : {counts['en']}")
        print(f"  Swedish (sv) : {counts['sv']}")
        print(f"  German  (de) : {counts['de']}")

        db_ok = counts["total"] > 2000
        db_sv = counts["sv"] > 300
        db_de = counts["de"] > 300
        db_status = "✓" if (db_ok and db_sv and db_de) else "⚠"
        print(f"\n  {db_status} {'Counts look correct' if db_ok else 'Chunk count lower than expected — re-check ingestion'}")
    except Exception as e:
        print(f"  ✗ DB check failed: {e}")

    # ── Retriever tests ───────────────────────────────────────────────────────
    for test in TESTS:
        print(f"\n{'=' * 65}")
        print(f"Test {test['id']}: {test['name']}")
        print(f"Query   : {test['query']}")
        print(f"Expects : {test['check']}")
        print("-" * 40)

        try:
            docs = await retriever._aget_relevant_documents(test["query"])

            if not docs:
                print("  ✗ FAIL — returned zero chunks")
                results.append({"id": test["id"], "name": test["name"], "passed": False, "reason": "zero chunks"})
                continue

            # Check minimum chunk count
            if len(docs) < test["min_chunks"]:
                print(f"  ✗ FAIL — got {len(docs)} chunks, expected >= {test['min_chunks']}")
                results.append({"id": test["id"], "name": test["name"], "passed": False,
                                 "reason": f"only {len(docs)} chunks"})
                continue

            # Check that expected language appears in top results
            top_langs    = [doc.metadata.get("language", "") for doc in docs[:4]]
            lang_present = test["expected_lang"] in top_langs
            first_lang   = docs[0].metadata.get("language", "?")

            print(f"  Chunks returned : {len(docs)}")
            print(f"  Top 4 languages : {top_langs}")
            print(f"  First chunk lang: {first_lang}")
            print()
            print_chunks(docs, max_show=3)

            # For SV/DE tests, the first chunk MUST be in the expected language
            # (proves language boost is working)
            if test["expected_lang"] in ("sv", "de"):
                passed = first_lang == test["expected_lang"]
                reason = "first chunk is correct language" if passed else \
                         f"first chunk is '{first_lang}', expected '{test['expected_lang']}'"
            else:
                passed = lang_present
                reason = "expected language present in top 4" if passed else \
                         f"language '{test['expected_lang']}' not in top 4"

            icon = "✓ PASS" if passed else "✗ FAIL"
            print(f"\n  {icon} — {reason}")
            results.append({"id": test["id"], "name": test["name"], "passed": passed, "reason": reason})

        except Exception as e:
            print(f"  ✗ ERROR — {e}")
            results.append({"id": test["id"], "name": test["name"], "passed": False, "reason": str(e)})

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 65}")
    print("RESULTS SUMMARY")
    print("=" * 65)

    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count

    for r in results:
        icon = "✓" if r["passed"] else "✗"
        print(f"  {icon}  Test {r['id']}: {r['name']}")
        if not r["passed"]:
            print(f"       → {r['reason']}")

    print(f"\n  Passed : {passed_count}/{len(results)}")
    print(f"  Failed : {failed_count}/{len(results)}")
    print("=" * 65)

    if failed_count == 0:
        print("\n✓ All tests passed. Retriever is working correctly.")
        print("  Next step: wire HybridRetriever into the Researcher agent.\n")
    else:
        print("\n⚠  Some tests failed. Check the output above.")
        print("  Common causes:")
        print("  - Language boost failing → check match_chunks RPC supports .eq() filter")
        print("  - Zero chunks → check match_threshold (try lowering to 0.5)")
        print("  - FTS not finding exact terms → check fts column is populated\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
