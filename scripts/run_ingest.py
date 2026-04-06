"""
scripts/run_ingest.py

One-time ingestion script. Run ONCE to load the entire regulatory corpus
into Supabase. After this, chunks sit permanently in document_chunks and
every user query searches against them — the PDFs are never touched again.

Usage:
    uv run python scripts/run_ingest.py

Re-run only when:
    - You add new documents to the corpus
    - You change chunking strategy and want to re-embed everything
    In both cases: clear the document_chunks table first to avoid duplicates.
"""

import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.ingest import ingest_document
from db.client import SYSTEM_USER_ID


# ─────────────────────────────────────────────────────────────────────────────
# CORPUS DEFINITION
# ─────────────────────────────────────────────────────────────────────────────
# user_id=SYSTEM_USER_ID → sentinel UUID "00000000-0000-0000-0000-000000000000"
# Platform-level docs — not tied to any real user.
# GDPR right-to-erasure will never target these rows.

CORPUS = [
    # ── Category 1: Regulatory Core ──────────────────────────────────────────
    {
        "path":       "data/regulatory/eu_ai_act_2024_en.pdf",
        "title":      "EU AI Act (English)",
        "doc_type":   "regulatory",
        "source_url": "https://eur-lex.europa.eu",
    },
    {
        "path":       "data/regulatory/eu_ai_act_2024_sv.pdf",
        "title":      "EU AI Act (Swedish)",
        "doc_type":   "regulatory",
        "source_url": "https://eur-lex.europa.eu",
    },
    {
        "path":       "data/regulatory/eu_ai_act_2024_de.pdf",
        "title":      "EU AI Act (German)",
        "doc_type":   "regulatory",
        "source_url": "https://eur-lex.europa.eu",
    },
    {
        "path":       "data/regulatory/gdpr_2016_679_en.pdf",
        "title":      "GDPR (English)",
        "doc_type":   "regulatory",
        "source_url": "https://eur-lex.europa.eu",
    },
    {
        "path":       "data/regulatory/gdpr_2016_679_sv.pdf",
        "title":      "GDPR (Swedish)",
        "doc_type":   "regulatory",
        "source_url": "https://eur-lex.europa.eu",
    },
    {
        "path":       "data/regulatory/ai_liability_directive_en.pdf",
        "title":      "AI Liability Directive (English)",
        "doc_type":   "regulatory",
        "source_url": "https://eur-lex.europa.eu",
    },

    # ── Category 2: Swedish Market Intelligence ───────────────────────────────
    {
        "path":       "data/swedish/digg_ai_vagledning_sv.pdf",
        "title":      "DIGG AI Vägledning (Swedish)",
        "doc_type":   "swedish_market",
        "source_url": "https://digg.se",
    },
    {
        "path":       "data/swedish/imy_gdpr_vagledning_sv.pdf",
        "title":      "IMY GDPR Vägledning (Swedish)",
        "doc_type":   "swedish_market",
        "source_url": "https://imy.se",
    },
    {
        "path":       "data/swedish/vinnova_ai_strategy_sv.pdf",
        "title":      "Vinnova AI Strategy (Swedish)",
        "doc_type":   "swedish_market",
        "source_url": "https://vinnova.se",
    },
    {
        "path":       "data/swedish/sweden_ai_commission_roadmap_en.pdf",
        "title":      "Sweden AI Commission Roadmap (English)",
        "doc_type":   "swedish_market",
        "source_url": "https://government.se",
    },
    {
        "path":       "data/swedish/sweden_government_ai_rapport_sv.pdf",
        "title":      "Sweden Government AI Rapport (Swedish)",
        "doc_type":   "swedish_market",
        "source_url": "https://government.se",
    },

    # ── Category 2: German Market Intelligence ────────────────────────────────
    {
        "path":       "data/german/ki_strategie_2023_de.pdf",
        "title":      "Nationale KI-Strategie 2023 (German)",
        "doc_type":   "german_market",
        "source_url": "https://bmbf.de",
    },
    {
        "path":       "data/german/bitkom_ki_leitfaden_de.pdf",
        "title":      "Bitkom KI Leitfaden (German)",
        "doc_type":   "german_market",
        "source_url": "https://bitkom.org",
    },
    {
        "path":       "data/german/baylda_ki_datenschutz_de.pdf",
        "title":      "BayLDA KI + Datenschutz (German)",
        "doc_type":   "german_market",
        "source_url": "https://lda.bayern.de",
    },
    {
        "path":       "data/german/ki_aktionsplan_2023_de.pdf",
        "title":      "KI Aktionsplan 2023 (German)",
        "doc_type":   "german_market",
        "source_url": "https://bmbf.de",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def run_all():
    project_root = Path(__file__).parent.parent
    results      = []
    total_chunks = 0
    start_all    = time.time()

    print("=" * 65)
    print("EU Regulatory Intelligence Agent — Corpus Ingestion")
    print("=" * 65)
    print(f"Documents to ingest: {len(CORPUS)}\n")

    for i, doc in enumerate(CORPUS, 1):
        file_path = project_root / doc["path"]
        label     = doc["title"]

        if not file_path.exists():
            print(f"[{i}/{len(CORPUS)}] SKIP — not found: {doc['path']}")
            results.append({
                "label":    label,
                "status":   "SKIPPED",
                "chunks":   0,
                "language": "-",
                "duration": 0,
            })
            continue

        print(f"[{i}/{len(CORPUS)}] Ingesting: {label}")
        start = time.time()

        try:
            result = await ingest_document(
                file_path=str(file_path),
                title=doc["title"],
                doc_type=doc["doc_type"],
                source_url=doc.get("source_url", ""),
                user_id=SYSTEM_USER_ID,   # ← UUID sentinel, not the string "system"
            )
            duration      = round(time.time() - start, 1)
            total_chunks += result["chunk_count"]

            results.append({
                "label":    label,
                "status":   "OK",
                "chunks":   result["chunk_count"],
                "language": result["language"],
                "duration": duration,
            })
            print(
                f"    ✓ {result['chunk_count']} chunks | "
                f"lang={result['language']} | "
                f"{duration}s\n"
            )

        except Exception as e:
            duration = round(time.time() - start, 1)
            print(f"    ✗ FAILED: {e}\n")
            results.append({
                "label":    label,
                "status":   f"FAILED: {e}",
                "chunks":   0,
                "language": "-",
                "duration": duration,
            })

    # ── Summary ───────────────────────────────────────────────────────────────
    total_duration = round(time.time() - start_all, 1)

    print("\n" + "=" * 65)
    print("INGESTION SUMMARY")
    print("=" * 65)
    print(f"{'Document':<45} {'St':<4} {'Chunks':<8} {'Lang':<6} Time")
    print("-" * 65)

    for r in results:
        icon = "✓" if r["status"] == "OK" else ("—" if "SKIPPED" in r["status"] else "✗")
        print(
            f"{r['label']:<45} "
            f"{icon:<4} "
            f"{r['chunks']:<8} "
            f"{r['language']:<6} "
            f"{r['duration']}s"
        )

    print("-" * 65)
    ok_count   = sum(1 for r in results if r["status"] == "OK")
    skip_count = sum(1 for r in results if "SKIPPED" in r["status"])
    fail_count = sum(1 for r in results if "FAILED" in r["status"])

    print(f"\nTotal chunks written : {total_chunks}")
    print(f"Succeeded            : {ok_count}/{len(CORPUS)}")
    print(f"Skipped              : {skip_count}")
    print(f"Failed               : {fail_count}")
    print(f"Total time           : {total_duration}s")
    print("=" * 65)

    if fail_count > 0:
        print("\n⚠  Some documents failed. Fix errors above.")
        print("   Clear failed docs from document_chunks before re-running.\n")
    else:
        print("\n✓ All documents ingested. Knowledge base is ready.")
        print("  Next: uv run python scripts/test_retriever.py\n")


if __name__ == "__main__":
    asyncio.run(run_all())
