-- Migration for databases created before 2026-09-03: adds per-issue
-- suggested reader questions (the chat rotates them as placeholder
-- suggestions). Fresh databases get the column from init_db.sql.
-- Safe to re-run.
ALTER TABLE issues
    ADD COLUMN IF NOT EXISTS suggested_questions JSONB NOT NULL DEFAULT '[]'::jsonb;
