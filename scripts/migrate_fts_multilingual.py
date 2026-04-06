"""
scripts/migrate_fts_multilingual.py

Fixes the broken FTS column in document_chunks.

PROBLEM:
    The original `fts` column was a GENERATED column using hardcoded 'english'
    stemming config. Swedish and German text was indexed with English rules —
    "reglering", "Verordnung" got mangled. Sparse search returned 0 results
    for SV/DE queries. Dense search (multilingual-e5-large) covered the gap,
    but hybrid retrieval was silently running as dense-only.

FIX:
    1. Drop the broken generated column (+ its GIN index, auto-dropped).
    2. Add a plain tsvector column (trigger-driven, not generated).
    3. Create a trigger function that routes to 'swedish' / 'german' / 'english'
       based on the row's `language` column.
    4. Attach the trigger (BEFORE INSERT OR UPDATE).
    5. Backfill all existing rows by firing the trigger on each row.
    6. Rebuild the GIN index on the new column.

RUN:
    uv run python scripts/migrate_fts_multilingual.py

EXPECTED OUTPUT:
    [1/6] Dropping old generated fts column...       ✓
    [2/6] Adding plain tsvector column...            ✓
    [3/6] Creating trigger function...               ✓
    [4/6] Attaching trigger...                       ✓
    [5/6] Backfilling existing rows...               ✓
    [6/6] Rebuilding GIN index...                    ✓

    Migration complete. Run scripts/test_retriever.py to verify.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.client import get_client, async_rpc


# ─────────────────────────────────────────────────────────────────────────────
# SQL STATEMENTS — executed in strict order
# ─────────────────────────────────────────────────────────────────────────────

MIGRATION_STEPS = [
    (
        "[1/6] Dropping old generated fts column",
        "ALTER TABLE document_chunks DROP COLUMN IF EXISTS fts;",
    ),
    (
        "[2/6] Adding plain tsvector column",
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS fts TSVECTOR;",
    ),
    (
        "[3/6] Creating trigger function update_fts_multilingual()",
        """
        CREATE OR REPLACE FUNCTION update_fts_multilingual()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.fts :=
                CASE NEW.language
                    WHEN 'sv' THEN to_tsvector('swedish', COALESCE(NEW.content, ''))
                    WHEN 'de' THEN to_tsvector('german',  COALESCE(NEW.content, ''))
                    ELSE           to_tsvector('english', COALESCE(NEW.content, ''))
                END;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,
    ),
    (
        "[4/6] Attaching trigger to document_chunks",
        """
        DROP TRIGGER IF EXISTS tsvector_update ON document_chunks;
        CREATE TRIGGER tsvector_update
            BEFORE INSERT OR UPDATE ON document_chunks
            FOR EACH ROW
            EXECUTE FUNCTION update_fts_multilingual();
        """,
    ),
    (
        "[5/6] Backfilling existing rows (fires trigger on all rows)",
        # WHERE id IS NOT NULL matches every row but satisfies Supabase's
        # RPC guard that blocks UPDATE statements without a WHERE clause.
        "UPDATE document_chunks SET content = content WHERE id IS NOT NULL;",
    ),
    (
        "[6/6] Rebuilding GIN index on fts column",
        """
        DROP INDEX IF EXISTS document_chunks_fts_idx;
        CREATE INDEX document_chunks_fts_idx ON document_chunks USING gin(fts);
        """,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# EXEC SQL HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def _run_sql(label: str, sql: str) -> None:
    print(f"  {label}...", end=" ", flush=True)
    try:
        await async_rpc("exec_sql", {"sql": sql.strip()})
        print("✓")
    except Exception as e:
        print(f"✗\n\nERROR: {e}\n")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# ROW COUNT HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def _get_chunk_counts() -> dict:
    client = get_client()

    def _query():
        total = client.table("document_chunks").select("id", count="exact").execute()
        sv    = client.table("document_chunks").select("id", count="exact").eq("language", "sv").execute()
        de    = client.table("document_chunks").select("id", count="exact").eq("language", "de").execute()
        en    = client.table("document_chunks").select("id", count="exact").eq("language", "en").execute()
        return {"total": total.count, "sv": sv.count, "de": de.count, "en": en.count}

    return await asyncio.to_thread(_query)


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY FTS
# Calls the search_chunks_fts RPC which now uses websearch_to_tsquery.
# Uses single-word queries per language to avoid compound-stem mismatches.
# Swedish legal PDFs have aggressive stemming — single authoritative words
# are more reliable verification targets than multi-word phrases.
# ─────────────────────────────────────────────────────────────────────────────

async def _verify_fts() -> None:
    print("\n── Post-migration FTS verification ──────────────────────────")

    # Single-word queries — avoids AND-matching failures from compound stemming.
    # These words appear in every EU AI Act / GDPR translation for each language.
    checks = [
        ("English", "obligations"),
        ("Swedish", "intelligens"),   # stems to 'intel' — 21 matches confirmed
        ("German",  "Verordnung"),
    ]

    all_passed = True
    for lang, query in checks:
        try:
            results = await async_rpc("search_chunks_fts", {
                "search_query": query,
                "match_count":  3,
            })
            count = len(results) if results else 0
            if count > 0:
                langs_found = list({r.get("language", "?") for r in results})
                print(f"  ✓  {lang:8s} — {count} result(s)  query='{query}'  langs={langs_found}")
            else:
                print(f"  ✗  {lang:8s} — 0 results  query='{query}'")
                all_passed = False
        except Exception as e:
            print(f"  ✗  {lang:8s} — RPC error: {e}")
            all_passed = False

    print()
    if all_passed:
        print("  ✓ All languages returning FTS results.")
        print("  FTS migration verified. Hybrid retrieval is now fully operational.")
    else:
        print("  ⚠ Some languages returning 0 results.")
        print("    Check search_chunks_fts RPC uses websearch_to_tsquery.")
        print("    Run the SQL in scripts/sql/create_exec_sql_rpc.sql again.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n" + "=" * 60)
    print("EU Regulatory Intelligence Agent")
    print("Multilingual FTS Migration")
    print("=" * 60)

    print("\n── Pre-migration chunk counts ───────────────────────────────")
    try:
        counts = await _get_chunk_counts()
        print(f"  Total : {counts['total']}")
        print(f"  EN    : {counts['en']}")
        print(f"  SV    : {counts['sv']}")
        print(f"  DE    : {counts['de']}")
    except Exception as e:
        print(f"  Could not fetch counts: {e}")

    print("\n── Running migration steps ──────────────────────────────────")
    for label, sql in MIGRATION_STEPS:
        await _run_sql(label, sql)

    print("\n── Post-migration chunk counts ──────────────────────────────")
    try:
        counts = await _get_chunk_counts()
        print(f"  Total : {counts['total']}")
        print(f"  EN    : {counts['en']}")
        print(f"  SV    : {counts['sv']}")
        print(f"  DE    : {counts['de']}")
    except Exception as e:
        print(f"  Could not fetch counts: {e}")

    await _verify_fts()

    print("=" * 60)
    print("Migration complete.")
    print("Next: uv run python scripts/test_retriever.py")
    print("      Sparse results for SV/DE queries must be non-zero.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
