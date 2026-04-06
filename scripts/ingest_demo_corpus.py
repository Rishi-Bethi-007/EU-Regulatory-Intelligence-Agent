"""
scripts/ingest_demo_corpus.py

Ingests the curated demo corpus for the EU Regulatory Intelligence Agent.

Documents chosen for maximum demo impact:
    1. Teknikföretagen — AI: Begynnelsen av ett paradigmskifte (Swedish manufacturing AI)
       Perfect for Swedish SME demo queries. 4500 member companies, 1/3 of Sweden's exports.

    2. IMY — GDPR vid användning av generativ AI (2025, Swedish)
       Official Swedish DPA guidance on GDPR + generative AI. Direct from the regulator.
       Covers: data minimisation, legal basis, automated decision-making, roles.

    3. IMY — AI-förordningen presentation (2024, Swedish)
       IMY's own slide deck explaining the EU AI Act to Swedish organisations.
       Covers: risk tiers, sandbox, timeline, Art. 13 transparency requirements.

    4. Vinnova/Tillväxtverket — Svenska SMF:s AI-kompetens (2024, Swedish)
       Swedish government report on AI competence in Swedish SMEs.
       Directly relevant to your target audience — Swedish SMEs.

    5. EU AI Act — Official text from EUR-Lex (English)
       The primary source. Ensures the corpus has the actual legislative text.

    6. EDPB Opinion 28/2024 — AI models and GDPR (English)
       European Data Protection Board opinion on AI models + personal data.
       Critical for GDPR + AI intersection queries.

Usage:
    uv run python scripts/ingest_demo_corpus.py

    Ingests all documents. Safe to re-run — checks for duplicates by title.
    Takes ~10-15 minutes depending on document sizes.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.ingest import ingest_document
from db.client import get_supabase_client


# ─────────────────────────────────────────────────────────────────────────────
# DEMO CORPUS — 6 documents chosen for demo coverage
# ─────────────────────────────────────────────────────────────────────────────

DEMO_CORPUS = [
    {
        "url":      "https://www.teknikforetagen.se/globalassets/rapporter--publikationer/ai---begynnelsen-av-ett-paradigmskifte.pdf",
        "title":    "Teknikföretagen — AI: Begynnelsen av ett paradigmskifte",
        "doc_type": "swedish_market",
        "language": "sv",
        "why":      "Swedish manufacturing industry AI report. 4500 member companies. Shows Swedish SME AI landscape.",
    },
    {
        "url":      "https://www.imy.se/contentassets/1571d42dcc8346529658968c198cd4b5/gdpr-vid-anvandning-av-generativ-ai_imy-2024-9162.pdf",
        "title":    "IMY — GDPR vid användning av generativ AI (2025)",
        "doc_type": "regulatory",
        "language": "sv",
        "why":      "Official Swedish DPA (IMY) guidance on GDPR + generative AI. Direct from the regulator.",
    },
    {
        "url":      "https://www.imy.se/globalassets/dokument/utbildningar-presentationer/vart-att-veta-om-ai-forordningen-27-september-2024.pdf",
        "title":    "IMY — Värt att veta om AI-förordningen (2024)",
        "doc_type": "regulatory",
        "language": "sv",
        "why":      "IMY presentation on EU AI Act for Swedish organisations. Covers risk tiers, Art.13, sandbox.",
    },
    {
        "url":      "https://tillvaxtverket.se/download/18.19d85e0e1961e0c5e2e28ca/1744272027800/Svenska-SMFs-AI-kompetens.pdf",
        "title":    "Tillväxtverket — Svenska SMF:s AI-kompetens (2024)",
        "doc_type": "swedish_market",
        "language": "sv",
        "why":      "Swedish government report on AI competence in Swedish SMEs. Your exact target audience.",
    },
    {
        "url":      "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401689",
        "title":    "EU AI Act — Regulation (EU) 2024/1689 — Official Text",
        "doc_type": "regulatory",
        "language": "en",
        "why":      "The primary legislative source. Ensures corpus has authoritative EU AI Act text.",
    },
    {
        "url":      "https://www.edpb.europa.eu/system/files/2024-12/edpb_opinion_202428_ai-models_en.pdf",
        "title":    "EDPB Opinion 28/2024 — AI Models and Personal Data",
        "doc_type": "regulatory",
        "language": "en",
        "why":      "European DPB opinion on AI models + GDPR. Critical for GDPR+AI intersection queries.",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def already_ingested(title: str) -> bool:
    """Check if a document with this title already exists in the corpus."""
    try:
        client = get_supabase_client()
        result = client.table("documents").select("id").eq("title", title).execute()
        return len(result.data) > 0
    except Exception:
        return False


async def download_and_ingest(doc: dict, index: int, total: int) -> bool:
    """Download a PDF from URL and ingest it into the corpus."""
    import httpx
    import tempfile

    title    = doc["title"]
    url      = doc["url"]
    doc_type = doc["doc_type"]

    print(f"\n[{index}/{total}] {title}")
    print(f"         URL: {url[:70]}...")

    # Check for duplicates
    if await already_ingested(title):
        print(f"         SKIP — already in corpus")
        return True

    # Download PDF
    print(f"         Downloading...")
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                print(f"         FAIL — HTTP {response.status_code}")
                return False
            pdf_bytes = response.content
            print(f"         Downloaded {len(pdf_bytes):,} bytes")
    except Exception as e:
        print(f"         FAIL — Download error: {e}")
        return False

    # Save to temp file and ingest
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        from db.client import SYSTEM_USER_ID
        result = await ingest_document(
            file_path=tmp_path,
            title=title,
            doc_type=doc_type,
            source_url=url,
            user_id=SYSTEM_USER_ID,
        )

        Path(tmp_path).unlink(missing_ok=True)

        print(f"         OK — {result['chunk_count']} chunks, lang={result['language']}")
        return True

    except Exception as e:
        print(f"         FAIL — Ingestion error: {e}")
        return False


async def main():
    print("=" * 60)
    print("EU Regulatory Intelligence Agent — Demo Corpus Ingestion")
    print("=" * 60)
    print(f"\nIngesting {len(DEMO_CORPUS)} documents...\n")

    for doc in DEMO_CORPUS:
        print(f"  Why: {doc['why']}")

    print()

    results = []
    for i, doc in enumerate(DEMO_CORPUS, 1):
        success = await download_and_ingest(doc, i, len(DEMO_CORPUS))
        results.append((doc["title"], success))

    # Summary
    print(f"\n{'=' * 60}")
    print("Ingestion complete:")
    for title, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {title[:55]}...")

    succeeded = sum(1 for _, s in results if s)
    print(f"\n{succeeded}/{len(DEMO_CORPUS)} documents ingested successfully.")

    if succeeded == len(DEMO_CORPUS):
        print("\nAll documents ingested. Run RAGAS baseline next:")
        print("  uv run python scripts/run_ragas_baseline.py")
    else:
        failed = [t for t, s in results if not s]
        print(f"\nFailed documents — retry manually:")
        for t in failed:
            print(f"  - {t}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
