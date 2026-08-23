-- =============================================================================
-- 009_partition_silver_fct_daily_prices.sql
-- Range Partitioning for silver.fct_daily_prices by scrape_date (Monthly Partitions)
-- =============================================================================

-- 1. Backup existing data to temporary table
CREATE TEMP TABLE tmp_fct_daily_prices_backup AS
SELECT * FROM silver.fct_daily_prices;

-- 2. Drop dependent views temporarily
--    (fct_daily_prices_imputed and gold.v_coverage are recreated below /
--     by the silver DAG's dbt run; v_promo_impact never existed upstream)
DROP VIEW IF EXISTS silver.fct_daily_prices_imputed CASCADE;
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

-- 8. Recreate dependent views dropped in step 2.
--    NOTE: gold.v_coverage below mirrors sql/views.sql §5 — keep the two in sync.
--    It requires silver.fct_daily_prices_imputed, which the silver DAG's
--    `dbt run` rebuilds (incremental). Skip gracefully if it is absent.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'silver'
          AND c.relname = 'fct_daily_prices_imputed'
          AND c.relkind IN ('r', 'p', 'v', 'm')
    ) THEN
        EXECUTE $sql$
            CREATE OR REPLACE VIEW gold.v_coverage AS
            SELECT
                d.scrape_date,
                d.store_slug,
                COUNT(*) AS total_observations,
                COUNT(DISTINCT d.product_key) AS unique_products,
                COUNT(*) FILTER (WHERE d.coicop_division = 'REVIEW') AS review_queue_count,
                ROUND(COUNT(*) FILTER (WHERE d.coicop_division <> 'REVIEW')::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 2) AS classification_rate_pct,
                COUNT(*) FILTER (WHERE m.barcode IS NOT NULL) AS barcode_count,
                ROUND(COUNT(*) FILTER (WHERE m.barcode IS NOT NULL)::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 2) AS barcode_coverage_pct,
                COUNT(*) FILTER (WHERE d.is_outlier = TRUE) AS outlier_count,
                COALESCE(imp.imputed_count, 0) AS imputed_count,
                ROUND(COALESCE(imp.imputed_count, 0)::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 2) AS imputation_rate_pct
            FROM silver.fct_daily_prices d
            LEFT JOIN silver.dim_items m ON m.item_id::text = d.item_id
            LEFT JOIN (
                SELECT scrape_date, store_slug, COUNT(*) AS imputed_count
                FROM silver.fct_daily_prices_imputed
                WHERE is_imputed = TRUE
                GROUP BY scrape_date, store_slug
            ) imp ON imp.scrape_date = d.scrape_date AND imp.store_slug = d.store_slug
            GROUP BY d.scrape_date, d.store_slug, imp.imputed_count
            ORDER BY d.scrape_date DESC, d.store_slug
        $sql$;
        RAISE NOTICE 'gold.v_coverage recreated.';
    ELSE
        RAISE NOTICE 'Skipped gold.v_coverage: run silver DAG dbt job (or \\i sql/views.sql) to restore it.';
    END IF;
END $$;
