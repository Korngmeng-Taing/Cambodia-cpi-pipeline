-- Create schema for gold standard data
CREATE SCHEMA IF NOT EXISTS gold;

-- Create the Gold Standard classification table
CREATE TABLE IF NOT EXISTS gold.product_classification (
    item_id VARCHAR(255) PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    gold_coicop_code VARCHAR(20) NOT NULL,
    verified_by VARCHAR(100),
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

-- Index for fast lookup by item_id
CREATE INDEX IF NOT EXISTS idx_gold_item_id ON gold.product_classification(item_id);

COMMENT ON TABLE gold.product_classification IS 'The ground truth classification table. Verified by human experts.';
