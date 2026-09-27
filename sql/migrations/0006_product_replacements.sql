-- Migration 0006: Product Replacements and Quality Adjustment Audit Table
-- Supports linking disappearing products to their successors with quality/quantity adjustment factors.

CREATE TABLE IF NOT EXISTS silver.dim_product_replacements (
    replacement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    old_item_id VARCHAR(100) NOT NULL,
    new_item_id VARCHAR(100) NOT NULL,
    replacement_date DATE NOT NULL,
    coicop_code VARCHAR(20) NOT NULL,
    store_slug VARCHAR(50) NOT NULL,
    replacement_type VARCHAR(30) NOT NULL, -- 'DIRECT_EQUIVALENT', 'QUANTITY_ADJUSTED', 'HEDONIC_ADJUSTED'
    quality_adjustment_factor NUMERIC(10, 6) DEFAULT 1.0,
    spec_differences JSONB,
    confidence_score NUMERIC(5, 4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_product_replacements_old_item ON silver.dim_product_replacements (old_item_id);
CREATE INDEX IF NOT EXISTS idx_product_replacements_new_item ON silver.dim_product_replacements (new_item_id);
CREATE INDEX IF NOT EXISTS idx_product_replacements_date ON silver.dim_product_replacements (replacement_date);
