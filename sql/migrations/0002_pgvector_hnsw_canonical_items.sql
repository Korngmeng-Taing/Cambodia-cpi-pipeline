-- ============================================================================
-- CAMBODIA CPI PIPELINE — MIGRATION 0002: PGVECTOR & HNSW INDEXING
-- Enables native PostgreSQL 16 vector search on silver.canonical_items (768-dim)
-- ============================================================================

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector extension not available in this PostgreSQL environment; skipping.';
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        -- 1. Add 768-dimensional vector embedding column to canonical items
        ALTER TABLE silver.canonical_items ADD COLUMN IF NOT EXISTS embedding vector(768);

        -- 2. Create Hierarchical Navigable Small World (HNSW) index for sub-millisecond cosine search
        CREATE INDEX IF NOT EXISTS idx_canonical_items_hnsw 
        ON silver.canonical_items USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

        -- 3. Also allow 768-dim native vector in item_embedding_cache
        ALTER TABLE silver.item_embedding_cache ADD COLUMN IF NOT EXISTS embedding_vec vector(768);
        CREATE INDEX IF NOT EXISTS idx_item_embedding_cache_vec_hnsw
        ON silver.item_embedding_cache USING hnsw (embedding_vec vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

        RAISE NOTICE 'pgvector and HNSW index successfully created on silver.canonical_items.';
    ELSE
        RAISE NOTICE 'pgvector extension not active; table remains operational without native vector column.';
    END IF;

    -- 4. Ensure item_match_log check constraint includes 'vector_embedding' and 'exact_text'
    BEGIN
        ALTER TABLE silver.item_match_log DROP CONSTRAINT IF EXISTS item_match_log_match_method_check;
        ALTER TABLE silver.item_match_log ADD CONSTRAINT item_match_log_match_method_check 
        CHECK (match_method IN ('barcode_exact', 'sku_exact', 'fuzzy_text', 'new_item', 'exact_text', 'vector_embedding'));
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Constraint update skipped or not applicable.';
    END;
END $$;
