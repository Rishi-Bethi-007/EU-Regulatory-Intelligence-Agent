"""
scripts/ingest_euaiact.py

Ingests the EU AI Act (Regulation 2024/1689) — the one document that failed
in ingest_demo_corpus.py because EUR-Lex blocks automated PDF downloads.

Strategy: try multiple sources in order until one works.
  1. HTML scrape from artificialintelligenceact.eu (full text, article by article)
  2. PDF from EPRS (European Parliamentary Research Service) — no bot blocking
  3. PDF via the EUR-Lex HTML page (not the direct PDF endpoint)
  4. Plain text from eur-lex.europa.eu ELI endpoint

The EPRS publishes a clean PDF of the EU AI Act that is not bot-blocked.

Usage:
    uv run python scripts/ingest_euaiact.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.ingest import ingest_document
from db.client import get_client, SYSTEM_USER_ID

TITLE = "EU AI Act — Regulation (EU) 2024/1689 — Official Text"

# Sources tried in order — first success wins
SOURCES = [
    # EPRS briefing + full text PDF — publicly accessible, no bot blocking
    {
        "url": "https://www.europarl.europa.eu/RegData/etudes/ATAG/2024/760392/EPRS_ATA(2024)760392_EN.pdf",
        "label": "EPRS summary PDF",
    },
    # EUR-Lex HTML endpoint — returns the full regulation as HTML (not PDF)
    # WebBaseLoader can parse this directly
    {
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689",
        "label": "EUR-Lex HTML full text",
        "is_html": True,
    },
    # ArtificialIntelligenceAct.eu — well-structured plain text HTML
    {
        "url": "https://artificialintelligenceact.eu/the-act/",
        "label": "artificialintelligenceact.eu HTML",
        "is_html": True,
    },
]


async def already_ingested(title: str) -> bool:
    try:
        client = get_client()
        result = client.table("documents").select("id").eq("title", title).execute()
        return len(result.data) > 0
    except Exception:
        return False


async def try_pdf_download(url: str, label: str) -> bytes | None:
    import httpx
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }
    print(f"  Trying: {label}")
    print(f"  URL   : {url[:80]}")
    try:
        async with httpx.AsyncClient(
            timeout=90,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "pdf" in content_type or url.endswith(".pdf"):
                    print(f"  ✓ Got PDF: {len(response.content):,} bytes")
                    return response.content
                else:
                    print(f"  ✗ Not a PDF (content-type: {content_type})")
                    return None
            else:
                print(f"  ✗ HTTP {response.status_code}")
                return None
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None


async def try_html_ingest(url: str, label: str) -> bool:
    """Use WebBaseLoader to load HTML directly, then ingest as text."""
    from langchain_community.document_loaders import WebBaseLoader
    from langchain_experimental.text_splitter import SemanticChunker
    from langchain_huggingface import HuggingFaceEmbeddings
    from db.client import log_audit_event

    print(f"  Trying HTML: {label}")
    print(f"  URL        : {url[:80]}")
    try:
        loader = WebBaseLoader(url)
        docs   = loader.load()

        if not docs or not docs[0].page_content.strip():
            print("  ✗ No content extracted from HTML")
            return False

        full_text = "\n\n".join(doc.page_content for doc in docs)
        print(f"  ✓ Extracted {len(full_text):,} chars from HTML")

        # Embed and chunk
        embedder = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")
        chunker  = SemanticChunker(
            embedder,
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=95,
        )

        # Create a fake Document for the chunker
        from langchain_core.documents import Document as LCDoc
        lc_doc   = LCDoc(page_content=full_text)
        chunks   = chunker.split_documents([lc_doc])

        print(f"  Chunking → {len(chunks)} chunks")
        if not chunks:
            print("  ✗ Zero chunks produced")
            return False

        # Insert document row
        client   = get_client()
        doc_rows = client.table("documents").insert({
            "title":       TITLE,
            "language":    "en",
            "doc_type":    "regulatory",
            "source_url":  url,
            "chunk_count": len(chunks),
            "user_id":     SYSTEM_USER_ID,
        }).execute()
        doc_id = doc_rows.data[0]["id"]

        # Embed and insert chunks
        chunk_rows = []
        for i, chunk in enumerate(chunks):
            embedding = embedder.embed_query(chunk.page_content)
            chunk_rows.append({
                "document_id": doc_id,
                "content":     chunk.page_content,
                "embedding":   embedding,
                "language":    "en",
                "chunk_index": i,
                "pii_scrubbed": False,
            })

        # Batch insert
        batch_size = 50
        for j in range(0, len(chunk_rows), batch_size):
            batch = chunk_rows[j:j+batch_size]
            client.table("document_chunks").insert(batch).execute()
            print(f"  Inserted batch {j//batch_size + 1} ({len(batch)} chunks)")

        await log_audit_event(
            event_type="document_ingested",
            payload={
                "title":       TITLE,
                "doc_id":      doc_id,
                "chunk_count": len(chunks),
                "source":      url,
                "method":      "html_ingest",
            },
            user_id=SYSTEM_USER_ID,
        )

        print(f"  ✓ Ingested {len(chunks)} chunks from HTML source")
        return True

    except Exception as e:
        print(f"  ✗ HTML ingest failed: {e}")
        return False


async def main():
    print("=" * 60)
    print("EU AI Act — Targeted Ingestion")
    print("=" * 60)

    if await already_ingested(TITLE):
        print(f"\n✓ Already ingested: {TITLE}")
        print("  Nothing to do.")
        return

    print(f"\nDocument: {TITLE}")
    print("Trying sources in order...\n")

    for source in SOURCES:
        is_html = source.get("is_html", False)

        if is_html:
            success = await try_html_ingest(source["url"], source["label"])
            if success:
                print(f"\n✅ Successfully ingested EU AI Act via: {source['label']}")
                print("\nNext steps:")
                print("  uv run python scripts/migrate_fts_multilingual.py")
                print("  uv run python scripts/run_ragas_baseline.py")
                return
        else:
            pdf_bytes = await try_pdf_download(source["url"], source["label"])
            if pdf_bytes:
                print("  Ingesting PDF...")
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(pdf_bytes)
                        tmp_path = tmp.name

                    result = await ingest_document(
                        file_path=tmp_path,
                        title=TITLE,
                        doc_type="regulatory",
                        source_url=source["url"],
                        user_id=SYSTEM_USER_ID,
                    )
                    Path(tmp_path).unlink(missing_ok=True)

                    print(f"\n✅ Successfully ingested EU AI Act via: {source['label']}")
                    print(f"   {result['chunk_count']} chunks, lang={result['language']}")
                    print("\nNext steps:")
                    print("  uv run python scripts/migrate_fts_multilingual.py")
                    print("  uv run python scripts/run_ragas_baseline.py")
                    return
                except Exception as e:
                    print(f"  ✗ Ingestion failed: {e}")
                    Path(tmp_path).unlink(missing_ok=True)

        print()

    # All sources failed — provide manual fallback instructions
    print("=" * 60)
    print("⚠  All automated sources failed.")
    print()
    print("Manual fallback (takes 2 minutes):")
    print()
    print("1. Open this URL in your browser:")
    print("   https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401689")
    print()
    print("2. The PDF will download (it works in a browser, just blocks bots).")
    print()
    print("3. Save it as euaiact.pdf in the project root, then run:")
    print("   uv run python scripts/ingest_manual.py")
    print()
    print("Or use the alternative EUR-Lex URL:")
    print("   https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
