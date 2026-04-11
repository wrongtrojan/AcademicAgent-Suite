-- ContextMap core schema (PostgreSQL 14+) — applied on first DB init

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    type TEXT NOT NULL CHECK (type IN ('pdf', 'video')),
    status TEXT NOT NULL DEFAULT 'Uploading',
    upload_path TEXT NOT NULL,
    process_path TEXT,
    structure_template TEXT,
    structure_outline JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ext_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_assets_status ON assets (status);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets (type);

CREATE TABLE IF NOT EXISTS asset_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assets_id UUID NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
    content TEXT,
    visual_description TEXT,
    type TEXT NOT NULL DEFAULT 'text',
    coordination JSONB NOT NULL DEFAULT '{}'::jsonb,
    dense_embedding REAL[],
    sparse_embedding JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_asset_chunks_asset ON asset_chunks (assets_id);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    status TEXT NOT NULL DEFAULT 'Idle',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term INT NOT NULL,
    session_id UUID NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'llm', 'system')),
    content TEXT NOT NULL,
    citations JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, term)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id);

CREATE TABLE IF NOT EXISTS knowledge_entities (
    id UUID PRIMARY KEY,
    categories TEXT[] NOT NULL DEFAULT '{}',
    canonical_name TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT,
    globel_vector REAL[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_entities_name ON knowledge_entities (canonical_name);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entities_id UUID NOT NULL REFERENCES knowledge_entities (id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES asset_chunks (id) ON DELETE CASCADE,
    confidence REAL NOT NULL DEFAULT 1.0,
    context TEXT
);

CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity ON entity_mentions (entities_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_chunk ON entity_mentions (chunk_id);

CREATE TABLE IF NOT EXISTS prompts (
    slug TEXT PRIMARY KEY,
    template TEXT NOT NULL,
    provider TEXT,
    schema JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS expert_register (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name TEXT NOT NULL,
    email TEXT UNIQUE,
    roles TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    expert_id UUID REFERENCES expert_register (id) ON DELETE SET NULL,
    entity_id UUID REFERENCES knowledge_entities (id) ON DELETE SET NULL,
    field_name TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs (entity_id);

CREATE TABLE IF NOT EXISTS job_records (
    job_id UUID PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    service TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Full-text (BM25-like via ts_rank_cd); same as shared/database/migrations/002_fulltext_embedding.sql
ALTER TABLE asset_chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_asset_chunks_content_tsv ON asset_chunks USING GIN (content_tsv);
