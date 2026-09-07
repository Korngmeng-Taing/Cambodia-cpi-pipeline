-- ============================================================================
-- CAMBODIA CPI PIPELINE — MIGRATION 0003: DECLARATIVE TABLE PARTITIONING
-- Partitions high-volume tables by date for query pruning and maintenance:
--   1. bronze.raw_prices (PARTITION BY RANGE (scraped_at))
--   2. silver.clean_store_prices (PARTITION BY RANGE (scrape_date))
-- Includes automated maintenance stored procedure: ops.maintain_monthly_partitions()
-- ============================================================================

-- Ensure ops schema exists
CREATE SCHEMA IF NOT EXISTS ops;

-- ----------------------------------------------------------------------------
-- 1. Helper function: Dynamically ensure a monthly partition exists
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ops.ensure_monthly_partition(
    p_schema_name TEXT,
    p_table_name TEXT,
    p_year INT,
    p_month INT
) RETURNS VOID AS $$
DECLARE
    v_part_name TEXT;
    v_start_date DATE;
    v_end_date DATE;
    v_sql TEXT;
BEGIN
    v_start_date := MAKE_DATE(p_year, p_month, 1);
    v_end_date := (v_start_date + INTERVAL '1 month')::DATE;
    v_part_name := FORMAT('%s_%s_%s', p_table_name, p_year, TO_CHAR(v_start_date, 'MM'));

    -- Check if partition already exists in pg_class
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = p_schema_name AND c.relname = v_part_name
    ) THEN
        v_sql := FORMAT(
            'CREATE TABLE IF NOT EXISTS %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L);',
            p_schema_name, v_part_name, p_schema_name, p_table_name,
            v_start_date, v_end_date
        );
        EXECUTE v_sql;
        RAISE NOTICE 'Created partition %.% from % to %', p_schema_name, v_part_name, v_start_date, v_end_date;
    END IF;
END;
$$ LANGUAGE plpgsql;


-- ----------------------------------------------------------------------------
-- 2. Stored Procedure: Proactive partition maintenance (N months ahead)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE ops.maintain_monthly_partitions(p_months_ahead INT DEFAULT 3)
AS $$
DECLARE
    v_curr_date DATE := CURRENT_DATE;
    v_target_date DATE;
    v_i INT;
    v_year INT;
    v_month INT;
    v_bronze_table TEXT;
    v_silver_table TEXT;
BEGIN
    -- Dynamically target 'raw_prices' if partitioned, else 'raw_prices_part'
    SELECT COALESCE(
        (SELECT c.relname FROM pg_class c
         JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'bronze' AND c.relname IN ('raw_prices', 'raw_prices_part') AND c.relkind = 'p'
         ORDER BY (c.relname = 'raw_prices') DESC LIMIT 1),
        'raw_prices_part'
    ) INTO v_bronze_table;

    -- Dynamically target 'clean_store_prices' if partitioned, else 'clean_store_prices_part'
    SELECT COALESCE(
        (SELECT c.relname FROM pg_class c
         JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'silver' AND c.relname IN ('clean_store_prices', 'clean_store_prices_part') AND c.relkind = 'p'
         ORDER BY (c.relname = 'clean_store_prices') DESC LIMIT 1),
        'clean_store_prices_part'
    ) INTO v_silver_table;

    FOR v_i IN 0..p_months_ahead LOOP
        v_target_date := (v_curr_date + (v_i || ' month')::INTERVAL)::DATE;
        v_year := EXTRACT(YEAR FROM v_target_date)::INT;
        v_month := EXTRACT(MONTH FROM v_target_date)::INT;

        -- Partition for bronze table
        PERFORM ops.ensure_monthly_partition('bronze', v_bronze_table, v_year, v_month);
        -- Partition for silver table
        PERFORM ops.ensure_monthly_partition('silver', v_silver_table, v_year, v_month);
    END LOOP;
END;
$$ LANGUAGE plpgsql;


-- ----------------------------------------------------------------------------
-- 3. Define Declaratively Partitioned Table Structures
-- ----------------------------------------------------------------------------

-- 3A. bronze.raw_prices_part
CREATE TABLE IF NOT EXISTS bronze.raw_prices_part (
    raw_price_id BIGINT NOT NULL,
    store_id VARCHAR(64) NOT NULL,
    item_description_raw TEXT NOT NULL,
    price NUMERIC(12,4) NOT NULL,
    currency VARCHAR(8) DEFAULT 'KHR',
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_url TEXT,
    source_name VARCHAR(128) NOT NULL,
    batch_id UUID,
    raw_payload JSONB,
    PRIMARY KEY (raw_price_id, scraped_at)
) PARTITION BY RANGE (scraped_at);

-- Sequence for raw_price_id if needed
CREATE SEQUENCE IF NOT EXISTS bronze.raw_prices_part_seq OWNED BY bronze.raw_prices_part.raw_price_id;
ALTER TABLE bronze.raw_prices_part ALTER COLUMN raw_price_id SET DEFAULT nextval('bronze.raw_prices_part_seq');

-- Catch-all default partition for bronze
CREATE TABLE IF NOT EXISTS bronze.raw_prices_part_default
    PARTITION OF bronze.raw_prices_part DEFAULT;

-- Partition indexes for bronze.raw_prices_part
CREATE INDEX IF NOT EXISTS idx_raw_prices_part_store_scraped 
    ON bronze.raw_prices_part (store_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_raw_prices_part_source_scraped 
    ON bronze.raw_prices_part (source_name, scraped_at);
CREATE INDEX IF NOT EXISTS idx_raw_prices_part_scraped_at 
    ON bronze.raw_prices_part (scraped_at);

-- BUG FIX: Use date-truncated scraped_at to enforce one observation per
-- item per store per day (matching original schema.sql dedup constraint).
-- Without the date cast, mid-day rescrapes create duplicate daily rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_prices_part_observation
    ON bronze.raw_prices_part (
        store_id, source_name,
        COALESCE(source_url, ''), item_description_raw,
        ((scraped_at AT TIME ZONE 'UTC')::date)
    );


-- 3B. silver.clean_store_prices_part
CREATE TABLE IF NOT EXISTS silver.clean_store_prices_part (
    raw_price_id BIGINT NOT NULL,
    scrape_date DATE NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    source_name VARCHAR(64),
    item_id TEXT,
    name_raw TEXT,
    name_clean TEXT,
    category_native TEXT,
    brand VARCHAR(256),
    barcode VARCHAR(64),
    currency VARCHAR(16),
    price_original_curr NUMERIC(14, 2),
    original_price_curr NUMERIC(14, 2),
    usd_khr_rate NUMERIC(10, 4),
    price_khr NUMERIC(14, 2),
    original_price_khr NUMERIC(14, 2),
    discount_pct NUMERIC(6, 2),
    on_promo BOOLEAN,
    size_norm VARCHAR(32),
    size_value NUMERIC(12, 4),
    size_unit VARCHAR(32),
    pack_qty INT,
    unit_price_khr NUMERIC(14, 2),
    coicop_division VARCHAR(16),
    coicop_code VARCHAR(16),
    coicop_method VARCHAR(32),
    coicop_confidence NUMERIC(5, 4),
    is_outlier BOOLEAN,
    cpi_eligible BOOLEAN,
    is_fallback BOOLEAN,
    fallback_reason TEXT,
    match_method VARCHAR(32),
    match_confidence NUMERIC(5, 4),
    scraped_at TIMESTAMPTZ,
    PRIMARY KEY (raw_price_id, scrape_date)
) PARTITION BY RANGE (scrape_date);

-- Catch-all default partition for silver
CREATE TABLE IF NOT EXISTS silver.clean_store_prices_part_default
    PARTITION OF silver.clean_store_prices_part DEFAULT;

-- BUG FIX: Removed "WHERE item_id IS NOT NULL" — PostgreSQL forbids partial
-- unique indexes on partitioned tables (ERROR: cannot create partial index).
CREATE UNIQUE INDEX IF NOT EXISTS uq_clean_store_prices_part_date_store_item
    ON silver.clean_store_prices_part (scrape_date, store_slug, item_id);

CREATE INDEX IF NOT EXISTS idx_clean_store_prices_part_scrape_date_store 
    ON silver.clean_store_prices_part (scrape_date, store_slug);

CREATE INDEX IF NOT EXISTS idx_clean_store_prices_part_scrape_date_brin 
    ON silver.clean_store_prices_part USING brin (scrape_date);

CREATE INDEX IF NOT EXISTS idx_clean_store_prices_part_store_item 
    ON silver.clean_store_prices_part (store_slug, item_id);

CREATE INDEX IF NOT EXISTS idx_clean_store_prices_part_coicop_code 
    ON silver.clean_store_prices_part (coicop_code);

CREATE INDEX IF NOT EXISTS idx_clean_store_prices_part_coicop_division 
    ON silver.clean_store_prices_part (coicop_division);


-- ----------------------------------------------------------------------------
-- 4. Pre-populate Monthly Partitions from 2026-07 through 2027-12
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    v_year INT;
    v_month INT;
BEGIN
    -- 2026 Partitions (Months 7 to 12)
    FOR v_month IN 7..12 LOOP
        PERFORM ops.ensure_monthly_partition('bronze', 'raw_prices_part', 2026, v_month);
        PERFORM ops.ensure_monthly_partition('silver', 'clean_store_prices_part', 2026, v_month);
    END LOOP;

    -- 2027 Partitions (Months 1 to 12)
    FOR v_month IN 1..12 LOOP
        PERFORM ops.ensure_monthly_partition('bronze', 'raw_prices_part', 2027, v_month);
        PERFORM ops.ensure_monthly_partition('silver', 'clean_store_prices_part', 2027, v_month);
    END LOOP;

    RAISE NOTICE 'Initial 2026-2027 monthly partitions successfully provisioned.';
END $$;


-- ----------------------------------------------------------------------------
-- 5. Safe Migration & Transition Guide
-- ----------------------------------------------------------------------------
-- To complete the transition in an active deployment without downtime:
--
-- STEP 1: Copy existing records to the partitioned staging tables:
--   INSERT INTO bronze.raw_prices_part SELECT * FROM bronze.raw_prices ON CONFLICT DO NOTHING;
--   INSERT INTO silver.clean_store_prices_part SELECT * FROM silver.clean_store_prices ON CONFLICT DO NOTHING;
--
-- STEP 2: Atomic Table Swap:
--   BEGIN;
--     ALTER TABLE bronze.raw_prices RENAME TO raw_prices_unpartitioned_backup;
--     ALTER TABLE bronze.raw_prices_part RENAME TO raw_prices;
--     ALTER TABLE silver.clean_store_prices RENAME TO clean_store_prices_unpartitioned_backup;
--     ALTER TABLE silver.clean_store_prices_part RENAME TO clean_store_prices;
--   COMMIT;
--
-- STEP 3: Verify with EXPLAIN ANALYZE:
--   EXPLAIN ANALYZE SELECT * FROM silver.clean_store_prices WHERE scrape_date = '2026-08-25';
--   (Query plan will show "Partitions pruned" scanning only clean_store_prices_2026_08).
-- ============================================================================
