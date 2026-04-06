"""
scripts/ingest_manual.py

Ingest a PDF that you've downloaded manually.

Usage:
    uv run python scripts/ingest_manual.py <path_to_pdf> <title> [doc_type] [language]

Examples:
    uv run python scripts/ingest_manual.py euaiact.pdf "EU AI Act — Regulation (EU) 2024/1689 — Official Text"
    uv run python scripts/ingest_manual.py gdpr.pdf "GDPR — Regulation (EU) 2016/679 — Official Text"
    uv run python scripts/ingest_manual.py bayda.pdf "BayLDA Checkliste KI-Systeme" regulatory de

Default doc_type: regulatory
Default language: auto-detected
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.ingest import ingest_document
from db.client import get_client, SYSTEM_USER_ID


async def already_ingested(title: str) -> bool:
    try:
        client = get_client()
        result = client.table("documents").select("id").eq("title", title).execute()
        return len(result.data) > 0
    except Exception:
        return False


async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    file_path = Path(sys.argv[1])
    title     = sys.argv[2]
    doc_type  = sys.argv[3] if len(sys.argv) > 3 else "regulatory"
    language  = sys.argv[4] if len(sys.argv) > 4 else None  # None = auto-detect

    if not file_path.exists():
        print(f"✗ File not found: {file_path}")
        sys.exit(1)

    print(f"\nFile    : {file_path}")
    print(f"Title   : {title}")
    print(f"Type    : {doc_type}")
    print(f"Language: {language or 'auto-detect'}")

    if await already_ingested(title):
        print(f"\n✓ Already ingested: {title}")
        sys.exit(0)

    print("\nIngesting...")
    try:
        result = await ingest_document(
            file_path=str(file_path),
            title=title,
            doc_type=doc_type,
            source_url=None,
            user_id=SYSTEM_USER_ID,
        )
        print(f"\n✅ Done: {result['chunk_count']} chunks, lang={result['language']}")
    except Exception as e:
        print(f"\n✗ Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
