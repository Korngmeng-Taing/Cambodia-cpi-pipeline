-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add a vector column to the gold table
-- 384 is the dimension for all-MiniLM-L6-v2, a common efficient embedding model
ALTER TABLE gold.product_classification 
ADD COLUMN IF NOT EXISTS embedding vector(384);

-- Create an HNSW index for lightning-fast semantic search
CREATE INDEX IF NOT EXISTS idx_gold_embedding_hnsw 
ON gold.product_classification 
USING hnsw (embedding vector_cosine_ops);

COMMENT ON COLUMN gold.product_classification.embedding IS 'Vector embedding of the canonical_name for semantic matching.';
