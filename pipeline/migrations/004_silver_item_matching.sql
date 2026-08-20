CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.canonical_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT NOT NULL,
    brand VARCHAR(256),
    barcode VARCHAR(64),
    size_norm VARCHAR(32),
    category VARCHAR(64),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_items_barcode ON silver.canonical_items(barcode) WHERE barcode IS NOT NULL;

CREATE TABLE IF NOT EXISTS silver.item_match_log (
    match_id BIGSERIAL PRIMARY KEY,
    raw_price_id BIGINT NOT NULL REFERENCES bronze.raw_prices(raw_price_id),
    item_id UUID NOT NULL REFERENCES silver.canonical_items(item_id),
    match_method VARCHAR(32) NOT NULL CHECK (match_method IN ('barcode_exact', 'sku_exact', 'fuzzy_text', 'new_item')),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    matched_by VARCHAR(64) DEFAULT 'auto'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_item_match_log_raw_price_id ON silver.item_match_log(raw_price_id);

CREATE TABLE IF NOT EXISTS silver.needs_review (
    review_id BIGSERIAL PRIMARY KEY,
    raw_price_id BIGINT NOT NULL,
    item_description_raw TEXT NOT NULL,
    best_match_item_id UUID,
    best_match_name TEXT,
    confidence NUMERIC(5,4),
    status VARCHAR(16) DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','skipped')),
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
