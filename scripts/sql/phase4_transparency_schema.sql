-- scripts/sql/phase4_transparency_schema.sql
--
-- Run in Supabase SQL Editor before running the transparency notice or
-- compliance scoring code.

-- ── research_runs: transparency notice + compliance score ─────────────────
ALTER TABLE research_runs
    ADD COLUMN IF NOT EXISTS transparency_notice TEXT,
    ADD COLUMN IF NOT EXISTS transparency_score  INTEGER DEFAULT 0;

-- ── Verify ────────────────────────────────────────────────────────────────
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'research_runs'
  AND column_name IN ('transparency_notice', 'transparency_score');
