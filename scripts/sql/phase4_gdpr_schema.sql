-- scripts/sql/phase4_gdpr_schema.sql
--
-- Run in Supabase SQL Editor before testing GDPR endpoints.
-- Adds columns required by Phase 4 API endpoints.

-- ── audit_events: add hash chain columns if not present ───────────────────
-- These are already written by db/client.py log_audit_event() —
-- this migration ensures the columns exist in the DB schema.
ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS previous_hash TEXT,
    ADD COLUMN IF NOT EXISTS event_hash    TEXT;

-- ── data_subjects: GDPR Art. 17 erasure records ───────────────────────────
-- One row per user who has requested erasure.
-- erasure_requested_at is the timestamp the DELETE endpoint was called.
CREATE TABLE IF NOT EXISTS data_subjects (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              TEXT NOT NULL,
    erasure_requested_at TIMESTAMPTZ NOT NULL,
    created_at           TIMESTAMPTZ DEFAULT now()
);

-- Unique constraint: one erasure record per user
CREATE UNIQUE INDEX IF NOT EXISTS data_subjects_user_id_idx
    ON data_subjects(user_id);

-- ── Verify ────────────────────────────────────────────────────────────────
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'audit_events'
  AND column_name IN ('previous_hash', 'event_hash');

SELECT table_name
FROM information_schema.tables
WHERE table_name = 'data_subjects';
