CREATE TABLE IF NOT EXISTS bronze.raw_prices (
    raw_price_id BIGSERIAL PRIMARY KEY,
    store_id VARCHAR(64) NOT NULL,
    item_description_raw TEXT NOT NULL,
    price NUMERIC(12,4) NOT NULL,
    currency VARCHAR(8) DEFAULT 'KHR',
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_url TEXT,
    source_name VARCHAR(128) NOT NULL,
    batch_id UUID,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_prices_store_scraped ON bronze.raw_prices (store_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_raw_prices_source_scraped ON bronze.raw_prices (source_name, scraped_at);

CREATE TABLE IF NOT EXISTS bronze.scrape_errors (
    error_id BIGSERIAL PRIMARY KEY,
    batch_id UUID,
    store_id VARCHAR(64),
    source_name VARCHAR(128),
    raw_record TEXT,
    error_type VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
