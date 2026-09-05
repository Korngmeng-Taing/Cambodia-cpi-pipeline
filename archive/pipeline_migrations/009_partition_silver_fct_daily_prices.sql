-- =============================================================================
-- 009_partition_silver_fct_daily_prices.sql
-- Range Partitioning for silver.fct_daily_prices by scrape_date (Monthly Partitions)
-- =============================================================================

-- 1. Backup existing data to temporary table
CREATE TEMP TABLE tmp_fct_daily_prices_backup AS
SELECT * FROM silver.fct_daily_prices;

-- 2. Drop dependent views temporarily
--    (gold.v_coverage is owned by sql/views.sql — the single source of truth.
--     It is recreated from there after this migration; see step 8.)
DROP VIEW IF EXISTS gold.v_coverage CASCADE;

-- 3. Drop existing non-partitioned table
DROP TABLE IF EXISTS silver.fct_daily_prices CASCADE;

-- 4. Create Master Partitioned Table
CREATE TABLE silver.fct_daily_prices (
    scrape_date DATE NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    item_id VARCHAR(128) NOT NULL,
    product_key VARCHAR(128) NOT NULL,
    name_clean TEXT,
    category_native TEXT,
    coicop_division VARCHAR(16),
    coicop_method VARCHAR(32),
    coicop_confidence NUMERIC(5, 4),
    currency VARCHAR(16),
    price_original_curr NUMERIC(14, 2),
    original_price_curr NUMERIC(14, 2),
    original_price_khr NUMERIC(14, 2),
    discount_pct NUMERIC(6, 2),
    on_promo BOOLEAN,
    price_khr NUMERIC(14, 2),
    unit_price_khr NUMERIC(14, 2),
    size_value NUMERIC(12, 4),
    size_unit VARCHAR(32),
    pack_qty INT,
    is_outlier BOOLEAN,
    cpi_eligible BOOLEAN,
    is_fallback BOOLEAN,
    scraped_at TIMESTAMPTZ,
    PRIMARY KEY (scrape_date, store_slug, item_id)
) PARTITION BY RANGE (scrape_date);

-- 5. Create Monthly Partitions for 2026 & 2027
CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2026_08 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2026_09 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2026_10 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2026_11 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2026_12 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2027_01 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2027_02 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2027-02-01') TO ('2027-03-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_2027_03 PARTITION OF silver.fct_daily_prices
    FOR VALUES FROM ('2027-03-01') TO ('2027-04-01');

CREATE TABLE IF NOT EXISTS silver.fct_daily_prices_default PARTITION OF silver.fct_daily_prices DEFAULT;

-- 6. Indexes for Partitioned Table
CREATE INDEX IF NOT EXISTS idx_fct_prices_date_store ON silver.fct_daily_prices(scrape_date, store_slug);
CREATE INDEX IF NOT EXISTS idx_fct_prices_item_id ON silver.fct_daily_prices(item_id);
CREATE INDEX IF NOT EXISTS idx_fct_prices_coicop ON silver.fct_daily_prices(coicop_division);

-- 7. Restore Data from Backup
INSERT INTO silver.fct_daily_prices
SELECT * FROM tmp_fct_daily_prices_backup;

DROP TABLE tmp_fct_daily_prices_backup;

-- 8. Serving views are owned by sql/views.sql (single source of truth —
--    built on gold.fct_daily_prices / gold.dim_items). Recreate manually
--    after running this migration:
--        psql -v ON_ERROR_STOP=1 -d cpi_db -f sql/views.sql
