-- ═══════════════════════════════════════════════════════════════════════════════
-- fts_migration_manual.sql
--
-- Run this ENTIRE BLOCK in Supabase SQL Editor (Dashboard → SQL Editor → New query)
-- Paste everything, click RUN. Takes ~5-10 seconds.
--
-- What this does:
--   1. Drops the old generated `fts` column (was using hardcoded 'english' config)
--   2. Adds a plain tsvector column
--   3. Creates a trigger that routes to 'swedish'/'german'/'english' by language
--   4. Attaches the trigger
--   5. Backfills existing rows — batched to avoid timeouts
--   6. Rebuilds the GIN index
--   7. Recreates search_chunks_fts() with correct per-language tsquery
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── Step 1: Drop old generated column ────────────────────────────────────────
ALTER TABLE document_chunks DROP COLUMN IF EXISTS fts;

-- ── Step 2: Add plain tsvector column ────────────────────────────────────────
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS fts TSVECTOR;

-- ── Step 3: Create trigger function ──────────────────────────────────────────
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

-- ── Step 4: Attach trigger ────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS tsvector_update ON document_chunks;

CREATE TRIGGER tsvector_update
    BEFORE INSERT OR UPDATE ON document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_fts_multilingual();

-- ── Step 5: Backfill existing rows ───────────────────────────────────────────
-- Update in batches of 500 to avoid statement timeout.
-- Each DO block handles one language to keep individual statements small.
DO $$
DECLARE
    batch_size  INT := 500;
    offset_val  INT := 0;
    rows_done   INT;
BEGIN
    LOOP
        UPDATE document_chunks
        SET fts = CASE language
                      WHEN 'sv' THEN to_tsvector('swedish', COALESCE(content, ''))
                      WHEN 'de' THEN to_tsvector('german',  COALESCE(content, ''))
                      ELSE           to_tsvector('english', COALESCE(content, ''))
                  END
        WHERE id IN (
            SELECT id FROM document_chunks
            ORDER BY id
            LIMIT batch_size OFFSET offset_val
        );

        GET DIAGNOSTICS rows_done = ROW_COUNT;
        EXIT WHEN rows_done = 0;
        offset_val := offset_val + batch_size;
    END LOOP;
END $$;

-- ── Step 6: Rebuild GIN index ─────────────────────────────────────────────────
DROP INDEX IF EXISTS document_chunks_fts_idx;
CREATE INDEX document_chunks_fts_idx ON document_chunks USING gin(fts);

-- ── Step 7: Recreate search_chunks_fts() with per-language config ─────────────
DROP FUNCTION IF EXISTS search_chunks_fts(text, integer);

CREATE FUNCTION search_chunks_fts(
    search_query text,
    match_count  int DEFAULT 10
)
RETURNS TABLE (
    id           uuid,
    content      text,
    document_id  uuid,
    language     text,
    chunk_index  int,
    similarity   float
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        dc.id,
        dc.content,
        dc.document_id,
        dc.language,
        dc.chunk_index,
        ts_rank(dc.fts, plainto_tsquery(
            CASE dc.language
                WHEN 'sv' THEN 'swedish'::regconfig
                WHEN 'de' THEN 'german'::regconfig
                ELSE           'english'::regconfig
            END,
            search_query
        ))::float AS similarity
    FROM document_chunks dc
    WHERE dc.fts @@ plainto_tsquery(
        CASE dc.language
            WHEN 'sv' THEN 'swedish'::regconfig
            WHEN 'de' THEN 'german'::regconfig
            ELSE           'english'::regconfig
        END,
        search_query
    )
    ORDER BY similarity DESC
    LIMIT match_count;
$$;

-- ── Verify ────────────────────────────────────────────────────────────────────
-- Run this SELECT after the above to confirm FTS is working:
SELECT language, count(*) AS chunks, count(fts) AS fts_populated
FROM document_chunks
GROUP BY language
ORDER BY language;
