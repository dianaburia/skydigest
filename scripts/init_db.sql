-- Enable pgvector for embedding storage and similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- articles: RSS feeds + APOD (Astronomy Picture of the Day)
-- Unique by URL: repeated ingestion of the same item is a no-op.
-- ============================================================================
CREATE TABLE IF NOT EXISTS articles (
    id           SERIAL PRIMARY KEY,
    source       TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    summary      TEXT,
    content      TEXT,
    image_url    TEXT,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_source       ON articles (source);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at DESC);

-- ============================================================================
-- papers: arXiv astro-ph submissions
-- Primary key is arxiv_id (version stripped) so re-ingest is idempotent.
-- ============================================================================
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    abstract     TEXT NOT NULL,
    authors      TEXT[] NOT NULL,
    categories   TEXT[] NOT NULL,
    url          TEXT NOT NULL,
    pdf_url      TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_papers_published_at ON papers (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_papers_categories   ON papers USING GIN (categories);

-- ============================================================================
-- space_weather: NOAA SWPC time-series metrics
-- Long, thin table: one row per (timestamp, metric) pair.
-- ============================================================================
CREATE TABLE IF NOT EXISTS space_weather (
    ts         TIMESTAMPTZ NOT NULL,
    metric     TEXT NOT NULL CHECK (metric IN ('kp', 'sw_speed', 'sw_density', 'bz')),
    value      DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ts, metric)
);

CREATE INDEX IF NOT EXISTS idx_space_weather_metric_ts ON space_weather (metric, ts DESC);

-- ============================================================================
-- chunks: text chunks with embeddings for the RAG pipeline
-- Deduped by (doc_type, doc_id, chunk_index); re-indexing is safe.
-- ============================================================================
CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    doc_type    TEXT NOT NULL CHECK (doc_type IN ('article', 'paper')),
    doc_id      TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(1024) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (doc_type, doc_id, chunk_index)
);

-- HNSW index for fast approximate nearest-neighbour search under cosine distance.
-- Cosine matches sentence-transformers embeddings normalized to unit length.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks (doc_type, doc_id);
