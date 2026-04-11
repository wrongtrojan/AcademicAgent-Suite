-- Full-text search column for BM25-like ranking (ts_rank_cd on tsvector)

ALTER TABLE asset_chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_asset_chunks_content_tsv ON asset_chunks USING GIN (content_tsv);
