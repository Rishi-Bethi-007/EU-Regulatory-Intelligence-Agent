-- scripts/sql/create_exec_sql_rpc.sql
--
-- Run this ONCE in Supabase SQL Editor before running migrate_fts_multilingual.py
--
-- Step 1: exec_sql helper (lets migration script run DDL via RPC)
-- Step 2: Drop + recreate search_chunks_fts with correct return signature

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1 — exec_sql RPC
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY: Supabase Python SDK has no raw SQL execution method.
-- This lets us call DDL statements from migrate_fts_multilingual.py via .rpc().
-- SECURITY: Only callable with service_role key. Drop after migrations if needed.

CREATE OR REPLACE FUNCTION exec_sql(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE sql;
END;
$$;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2 — search_chunks_fts RPC (drop first, then recreate)
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY DROP FIRST: Postgres 42P13 — cannot change return type of existing function.
-- CREATE OR REPLACE only works when the return signature is identical.
-- Our new version returns `float` similarity (ts_rank score) instead of the
-- previous return type — so we must drop and recreate.

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
