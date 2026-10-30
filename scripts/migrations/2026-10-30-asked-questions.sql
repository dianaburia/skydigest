-- Append-only log of real questions sent to /ask (eval-set raw material).
-- Run on prod BEFORE deploying the code that writes to it (the write is
-- best-effort, so nothing breaks either way — but questions would be lost).
CREATE TABLE IF NOT EXISTS asked_questions (
    id        BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    question  TEXT NOT NULL,
    retrieved JSONB NOT NULL DEFAULT '[]'::jsonb
);
