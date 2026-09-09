-- ============================================================================
-- CAMBODIA CPI PIPELINE — POSTGRESQL 16 RELATIONAL SCHEMA DDL
-- Schemas: staging (Bronze), silver (Clean observations & dims), gold (Index & stats)
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Required for trigram GIN indexes and high-dimensional vector search
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pg_trgm extension not available, continuing...';
END $$;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'vector extension not available, continuing...';
END $$;

-- ============================================================================
-- 0. BRONZE (Raw Store Listings & Errors)
-- Declarative Monthly Partitioning by scraped_at
-- ============================================================================

CREATE TABLE IF NOT EXISTS bronze.raw_prices (
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

CREATE SEQUENCE IF NOT EXISTS bronze.raw_prices_seq OWNED BY bronze.raw_prices.raw_price_id;
ALTER TABLE bronze.raw_prices ALTER COLUMN raw_price_id SET DEFAULT nextval('bronze.raw_prices_seq');

CREATE TABLE IF NOT EXISTS bronze.raw_prices_default
    PARTITION OF bronze.raw_prices DEFAULT;

CREATE INDEX IF NOT EXISTS idx_raw_prices_store_scraped ON bronze.raw_prices (store_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_raw_prices_source_scraped ON bronze.raw_prices (source_name, scraped_at);
CREATE INDEX IF NOT EXISTS idx_raw_prices_scraped_at ON bronze.raw_prices (scraped_at);
CREATE INDEX IF NOT EXISTS idx_raw_prices_observation ON bronze.raw_prices (
    store_id, source_name, item_description_raw, scraped_at
);

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

-- ============================================================================
-- 1. STAGING (Bronze Ingestion)
-- ============================================================================

-- Raw scrapes: one batch record per store per scrape day (upserted on re-run).
CREATE TABLE IF NOT EXISTS staging.raw_scrapes (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    scrape_date DATE NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    record_count INT NOT NULL DEFAULT 0,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_scrapes_day_store ON staging.raw_scrapes(scrape_date, store_slug);
CREATE INDEX IF NOT EXISTS idx_raw_scrapes_date_store ON staging.raw_scrapes(scrape_date, store_slug);
CREATE INDEX IF NOT EXISTS idx_raw_scrapes_run_id ON staging.raw_scrapes(run_id);

-- Exchange rates table: MEF USD/KHR official daily rate + fallback audit
CREATE TABLE IF NOT EXISTS staging.exchange_rates (
    execution_date DATE PRIMARY KEY,
    rate NUMERIC(10, 4) NOT NULL,
    source VARCHAR(32) NOT NULL, -- 'official', 'approx', 'constant'
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    raw_payload JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Bronze validation stats (parquet snapshots uploaded by Playwright scrapers)
CREATE TABLE IF NOT EXISTS staging.bronze_ingestion_stats (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(64) NOT NULL,
    scrape_date DATE NOT NULL,
    object_key TEXT,
    row_count INT NOT NULL,
    avg_row_count_7d NUMERIC(12, 2),
    price_nulls INT NOT NULL DEFAULT 0,
    price_negatives INT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL, -- 'PASSED', 'FAILED'
    validation_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bronze_stats_source_date UNIQUE (source_name, scrape_date)
);
CREATE INDEX IF NOT EXISTS idx_bronze_stats_status_date
    ON staging.bronze_ingestion_stats(status, scrape_date);

-- ============================================================================
-- 2. SILVER (Fact & Dimensions)
-- ============================================================================

-- Canonical items registry
CREATE TABLE IF NOT EXISTS silver.canonical_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT NOT NULL,
    brand VARCHAR(256),
    barcode VARCHAR(64),
    size_norm VARCHAR(32),
    coicop_division VARCHAR(16),
    coicop_code VARCHAR(16),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- Backwards-compatibility: drop the unused `category` column on existing installs; ensure coicop columns exist.
ALTER TABLE silver.canonical_items DROP COLUMN IF EXISTS category;
ALTER TABLE silver.canonical_items ADD COLUMN IF NOT EXISTS coicop_division VARCHAR(16);
ALTER TABLE silver.canonical_items ADD COLUMN IF NOT EXISTS coicop_code VARCHAR(16);
-- pgvector 768-dimensional product representation & HNSW index
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE silver.canonical_items ADD COLUMN IF NOT EXISTS embedding vector(768);
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_canonical_items_hnsw ON silver.canonical_items USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector HNSW index creation skipped on canonical_items';
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_items_barcode ON silver.canonical_items(barcode) WHERE barcode IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_items_name ON silver.canonical_items(canonical_name);
CREATE INDEX IF NOT EXISTS idx_canonical_items_lower_trim ON silver.canonical_items (lower(trim(canonical_name)));
CREATE INDEX IF NOT EXISTS idx_canonical_name_trgm ON silver.canonical_items USING gin (canonical_name gin_trgm_ops);

-- Item matching audit log
CREATE TABLE IF NOT EXISTS silver.item_match_log (
    match_id BIGSERIAL PRIMARY KEY,
    raw_price_id BIGINT NOT NULL,
    item_id UUID NOT NULL REFERENCES silver.canonical_items(item_id),
    match_method VARCHAR(32) NOT NULL CHECK (match_method IN ('barcode_exact', 'sku_exact', 'fuzzy_text', 'new_item', 'exact_text', 'vector_embedding')),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    matched_by VARCHAR(64) DEFAULT 'auto'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_item_match_log_raw_price_id ON silver.item_match_log(raw_price_id);
CREATE INDEX IF NOT EXISTS idx_item_match_log_item_id ON silver.item_match_log(item_id);

-- Review Queue for fuzzy matching and low-confidence classifications
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
    created_at TIMESTAMPTZ DEFAULT NOW(),
    -- C3 fix: UNIQUE on raw_price_id prevents duplicate review rows on Airflow retries
    CONSTRAINT uq_needs_review_raw_price_id UNIQUE (raw_price_id)
);
CREATE INDEX IF NOT EXISTS idx_needs_review_status ON silver.needs_review (status);
CREATE INDEX IF NOT EXISTS idx_needs_review_confidence ON silver.needs_review (confidence DESC);

-- AI COICOP Memoization Cache
CREATE TABLE IF NOT EXISTS silver.dim_coicop_ai_cache (
    product_name TEXT PRIMARY KEY,
    coicop_code VARCHAR(16) NOT NULL,
    confidence_score NUMERIC(5, 4),
    reasoning TEXT,
    model_version VARCHAR(64),
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- P3 #128 — Item Embedding Cache for VectorItemMatcher
-- Stores pre-computed embeddings for product names to avoid re-embedding on each run.
-- Columns:
--   item_id        : canonical_items.item_id (TEXT, since silver.canonical_items.item_id is TEXT)
--   product_name   : canonical_name from dim_canonical_products (or raw name)
--   embedding      : VECTOR(1536) or BYTEA for pgvector storage
--   model_name     : embedding model identifier (e.g., 'text-embedding-3-small')
--   created_at     : when the embedding was generated
--   updated_at     : for LRU eviction tracking
-- This table is looked up by pipeline/vector_item_matcher.py before calling the embedding API.
CREATE TABLE IF NOT EXISTS silver.item_embedding_cache (
    item_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    embedding BYTEA NOT NULL,          -- pgvector VECTOR(1536) serialized as BYTEA
    model_name VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_item_embedding_cache_model
    ON silver.item_embedding_cache(model_name);
CREATE INDEX IF NOT EXISTS idx_item_embedding_cache_updated
    ON silver.item_embedding_cache(updated_at DESC);

-- Canonical product dimension created by the canonicalization engine
CREATE TABLE IF NOT EXISTS silver.dim_canonical_products (
    canonical_item_id UUID PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    coicop_code VARCHAR(16),
    source_name VARCHAR(64),
    raw_item_id VARCHAR(128),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ml_confidence NUMERIC(5, 4),
    classification_method VARCHAR(32),
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_canonical_raw_item
    ON silver.dim_canonical_products(source_name, raw_item_id);

-- Silver Store Cleaned Fact Observation Table (Declarative Monthly Partitioning)
CREATE TABLE IF NOT EXISTS silver.clean_store_prices (
    raw_price_id BIGINT NOT NULL,
    scrape_date DATE NOT NULL,
    store_slug VARCHAR(64),
    source_name VARCHAR(128),
    item_id TEXT,
    name_raw TEXT,
    name_clean TEXT,
    category_native TEXT,
    brand TEXT,
    barcode TEXT,
    currency VARCHAR(8),
    price_original_curr NUMERIC,
    original_price_curr NUMERIC,
    usd_khr_rate NUMERIC,
    price_khr NUMERIC,
    original_price_khr NUMERIC,
    discount_pct NUMERIC,
    on_promo BOOLEAN,
    size_norm TEXT,
    size_value NUMERIC,
    size_unit TEXT,
    pack_qty INT,
    unit_price_khr NUMERIC,
    coicop_division TEXT,
    coicop_code TEXT,
    coicop_method TEXT,
    coicop_confidence NUMERIC,
    is_outlier BOOLEAN,
    cpi_eligible BOOLEAN,
    is_fallback BOOLEAN,
    fallback_reason TEXT,
    match_method TEXT,
    match_confidence NUMERIC,
    scraped_at TIMESTAMPTZ,
    PRIMARY KEY (raw_price_id, scrape_date)
) PARTITION BY RANGE (scrape_date);

CREATE TABLE IF NOT EXISTS silver.clean_store_prices_default
    PARTITION OF silver.clean_store_prices DEFAULT;

CREATE INDEX IF NOT EXISTS idx_clean_store_prices_scrape_date_store 
    ON silver.clean_store_prices (scrape_date, store_slug);
CREATE INDEX IF NOT EXISTS idx_clean_store_prices_scrape_date_brin 
    ON silver.clean_store_prices USING brin (scrape_date);
CREATE INDEX IF NOT EXISTS idx_clean_store_prices_store_item 
    ON silver.clean_store_prices (store_slug, item_id);
CREATE INDEX IF NOT EXISTS idx_clean_store_prices_coicop_code 
    ON silver.clean_store_prices (coicop_code);
CREATE INDEX IF NOT EXISTS idx_clean_store_prices_coicop_division 
    ON silver.clean_store_prices (coicop_division);

-- Gold Conformed Daily Price Fact Table (Essential Metrics & Foreign Keys)
CREATE TABLE IF NOT EXISTS gold.fct_daily_prices (
    scrape_date DATE NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    item_id TEXT NOT NULL,
    price_khr NUMERIC(14, 2) NOT NULL,
    original_price_khr NUMERIC(14, 2),
    discount_pct NUMERIC(6, 2),
    on_promo BOOLEAN,
    unit_price_khr NUMERIC(14, 2),
    size_value NUMERIC(12, 4),
    size_unit VARCHAR(32),
    pack_qty INT,
    cpi_eligible BOOLEAN,
    is_outlier BOOLEAN,
    is_fallback BOOLEAN,
    PRIMARY KEY (scrape_date, store_slug, item_id)
);

-- Gold Jevons Micro-Index Facts
CREATE TABLE IF NOT EXISTS gold.fct_elementary_indices (
    calculation_date DATE NOT NULL,
    item_id TEXT NOT NULL,
    coicop_division VARCHAR(10) NOT NULL,
    coicop_code VARCHAR(20),
    base_price_khr NUMERIC(14, 4),
    current_price_khr NUMERIC(14, 4),
    price_ratio NUMERIC(10, 6),
    price_ratio_pct NUMERIC(10, 4),
    elementary_index NUMERIC(10, 4),
    is_imputed BOOLEAN DEFAULT FALSE,
    observation_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (calculation_date, item_id)
);
CREATE INDEX IF NOT EXISTS idx_fct_elem_indices_date ON gold.fct_elementary_indices(calculation_date);
CREATE INDEX IF NOT EXISTS idx_fct_elem_indices_division ON gold.fct_elementary_indices(coicop_division);

-- Gold Daily Laspeyres 12-Division & Headline CPI Facts
CREATE TABLE IF NOT EXISTS gold.fct_cpi_daily (
    calculation_date DATE NOT NULL,
    coicop_division VARCHAR(10) NOT NULL,
    division_name VARCHAR(150),
    weight NUMERIC(8, 5),
    division_index NUMERIC(10, 4),
    headline_cpi NUMERIC(10, 4),
    core_cpi NUMERIC(10, 4),
    item_count INTEGER,
    observation_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (calculation_date, coicop_division)
);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_daily_date ON gold.fct_cpi_daily(calculation_date);

-- P3 #129 — Data-quality sanity rails on the daily CPI facts.
-- Headline/Core CPI for a 2020-base series must fall within ±50% of 100 (a literature-normal sanity bound).
-- The previous default of (50, 500) is a 5× envelope that catches catastrophic unit-price
-- corruption (e.g. wrong KHR/USD factor × 4000) but lets natural 25%-annual inflation through.
ALTER TABLE gold.fct_cpi_daily
    DROP CONSTRAINT IF EXISTS chk_fct_cpi_headline_range,
    DROP CONSTRAINT IF EXISTS chk_fct_cpi_core_range,
    DROP CONSTRAINT IF EXISTS chk_fct_cpi_division_index_range,
    DROP CONSTRAINT IF EXISTS chk_fct_cpi_weight_sum;
ALTER TABLE gold.fct_cpi_daily
    ADD CONSTRAINT chk_fct_cpi_headline_range
        CHECK (headline_cpi IS NULL OR (headline_cpi > 50 AND headline_cpi < 500)),
    ADD CONSTRAINT chk_fct_cpi_core_range
        CHECK (core_cpi IS NULL OR (core_cpi > 50 AND core_cpi < 500)),
    ADD CONSTRAINT chk_fct_cpi_division_index_range
        CHECK (division_index IS NULL OR (division_index > 30 AND division_index < 700)),
    ADD CONSTRAINT chk_fct_cpi_weight_sum
        CHECK (weight IS NULL OR (weight > 0 AND weight < 1));

-- Gold Monthly Laspeyres 12-Division & Headline CPI Facts
CREATE TABLE IF NOT EXISTS gold.fct_cpi_monthly (
    cpi_month DATE NOT NULL,
    coicop_division VARCHAR(10) NOT NULL,
    division_name VARCHAR(150),
    weight NUMERIC(8, 5),
    monthly_division_index NUMERIC(10, 4),
    monthly_headline_cpi NUMERIC(10, 4),
    monthly_core_cpi NUMERIC(10, 4),
    mom_inflation_pct NUMERIC(8, 4),
    yoy_inflation_pct NUMERIC(8, 4),
    item_count INTEGER,
    observation_count INTEGER,
    active_days_in_month INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cpi_month, coicop_division)
);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_monthly_month ON gold.fct_cpi_monthly(cpi_month);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_monthly_div ON gold.fct_cpi_monthly(coicop_division);


-- Gold Conformed Item Dimension (Master Catalog)
CREATE TABLE IF NOT EXISTS gold.dim_items (
    item_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    brand VARCHAR(256),
    barcode VARCHAR(64),
    size_norm VARCHAR(32),
    native_category TEXT,
    coicop_division VARCHAR(16),
    coicop_code VARCHAR(16),
    unit_of_measure VARCHAR(32),
    store_count INT DEFAULT 0,
    avg_match_confidence NUMERIC(5,4),
    first_seen DATE,
    last_seen DATE,
    is_active BOOLEAN DEFAULT TRUE,
    lifecycle_status VARCHAR(32),
    days_since_last_seen INT
);

-- Gold Conformed Store Dimension
CREATE TABLE IF NOT EXISTS gold.dim_stores (
    store_slug VARCHAR(64) PRIMARY KEY,
    store_name TEXT NOT NULL,
    source_type VARCHAR(32),
    channel VARCHAR(32),
    default_currency VARCHAR(8),
    default_coicop_division VARCHAR(16),
    is_active BOOLEAN DEFAULT TRUE,
    total_observations INT DEFAULT 0,
    distinct_products_count INT DEFAULT 0,
    first_scraped_at DATE,
    last_scraped_at DATE
);

-- Store Product Link Mapping
-- (removed: silver.store_products was a legacy table, link data now lives in dbt silver.item_match_log / dim_products)



-- Manual Overrides Table
CREATE TABLE IF NOT EXISTS silver.coicop_override (
    id SERIAL PRIMARY KEY,
    match_type VARCHAR(32) NOT NULL, -- 'product_key', 'barcode', 'sku', 'name'
    match_value TEXT NOT NULL,
    store_slug VARCHAR(64), -- NULL applies to all stores
    coicop_division VARCHAR(16) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_override_match ON silver.coicop_override(match_type, match_value);

-- Persistent Manual Overrides Table
-- Stores custom operator overrides without risk of being overwritten by seed refreshes.
-- int_coicop_classified can UNION this table with the seed at query time.
CREATE TABLE IF NOT EXISTS silver.coicop_override_manual (
    id SERIAL PRIMARY KEY,
    match_type VARCHAR(32) NOT NULL, -- 'product_key', 'barcode', 'name'
    match_value TEXT NOT NULL,
    store_slug VARCHAR(64), -- NULL applies to all stores
    coicop_division VARCHAR(16) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_coicop_override_manual ON silver.coicop_override_manual(match_type, match_value, (coalesce(store_slug, 'ALL')));
CREATE INDEX IF NOT EXISTS idx_override_manual_match ON silver.coicop_override_manual(match_type, match_value);

-- Store Native Category Mapping Table
CREATE TABLE IF NOT EXISTS silver.coicop_category_map (
    store_slug VARCHAR(64) NOT NULL,
    category_native TEXT NOT NULL,
    coicop_division VARCHAR(16) NOT NULL,
    PRIMARY KEY (store_slug, category_native)
);

-- Review Queue for Unclassified / Low-Confidence Rows
CREATE TABLE IF NOT EXISTS silver.classification_queue (
    id BIGSERIAL PRIMARY KEY,
    product_key VARCHAR(128) NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    name_clean TEXT NOT NULL,
    category_native TEXT,
    price_khr NUMERIC(14, 2),
    reason TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'RESOLVED', 'IGNORED'
    resolved_division VARCHAR(16),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_class_queue_pending ON silver.classification_queue(status) WHERE status = 'PENDING';



-- Golden Ground Truth Dataset (Active Learning & Human Validation)
CREATE TABLE IF NOT EXISTS silver.classification_ground_truth (
    id BIGSERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    coicop_code VARCHAR(16) NOT NULL,
    coicop_division VARCHAR(16) NOT NULL,
    verified_by VARCHAR(64) NOT NULL DEFAULT 'analyst',
    confidence_score NUMERIC(5, 4) NOT NULL DEFAULT 1.000,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ground_truth_product UNIQUE (product_name)
);
CREATE INDEX IF NOT EXISTS idx_ground_truth_division ON silver.classification_ground_truth(coicop_division);
CREATE INDEX IF NOT EXISTS idx_ground_truth_code ON silver.classification_ground_truth(coicop_code);

-- Hedonic Quality Adjustment Table (Division 09 / 08 Electronics)
CREATE TABLE IF NOT EXISTS silver.hedonic_adjusted_prices (
    scrape_date DATE NOT NULL,
    item_id VARCHAR(128) NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    canonical_name TEXT NOT NULL,
    coicop_division VARCHAR(16) NOT NULL,
    raw_price_khr NUMERIC(14, 2) NOT NULL,
    ram_gb INT NOT NULL DEFAULT 0,
    storage_gb INT NOT NULL DEFAULT 0,
    screen_inches NUMERIC(4, 2) DEFAULT 0.0,
    camera_mp INT DEFAULT 0,
    is_5g INT DEFAULT 0,
    hedonic_adjusted_price_khr NUMERIC(14, 2) NOT NULL,
    adjustment_ratio NUMERIC(8, 4) NOT NULL DEFAULT 1.0000,
    model_r2 NUMERIC(6, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scrape_date, item_id, store_slug)
);
CREATE INDEX IF NOT EXISTS idx_hedonic_date_div ON silver.hedonic_adjusted_prices(scrape_date, coicop_division);

-- ============================================================================
-- 3. GOLD (Star Schema, Official Weights & Anomaly Tables)
--
-- NOTE: Index-computation objects (base_prices, fct_daily_price_stats,
--       cpi_category_daily, cpi_headline_daily, cpi_geks_multilateral,
--       cpi_fisher_superlative, mart_cpi_daily, mart_cpi_division_daily)
--       are intentionally NOT created here. The Jevons/Laspeyres/GEKS/Fisher
--       calculation layer is planned but not implemented yet; re-add DDL when
--       that work lands.
-- ============================================================================

-- Official COICOP Division Weights
CREATE TABLE IF NOT EXISTS gold.coicop_weights (
    coicop_division VARCHAR(16) PRIMARY KEY,
    division_name TEXT NOT NULL,
    weight_pct NUMERIC(6, 3) NOT NULL, -- Exact weights summing to 100.000
    source TEXT NOT NULL,
    effective_date DATE NOT NULL DEFAULT '2026-08-01'
);

-- Daily Price Anomaly Detection (> 15% day-on-day shift)
CREATE TABLE IF NOT EXISTS gold.price_anomalies (
    id BIGSERIAL PRIMARY KEY,
    scrape_date DATE NOT NULL,
    item_id VARCHAR(128),
    product_key VARCHAR(128) NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    price_khr NUMERIC(14, 2) NOT NULL,
    expected_price_khr NUMERIC(14, 2) NOT NULL,
    pct_change NUMERIC(6, 2) NOT NULL,
    anomaly_type VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE gold.price_anomalies ADD COLUMN IF NOT EXISTS item_id VARCHAR(128);
CREATE INDEX IF NOT EXISTS idx_anomalies_date ON gold.price_anomalies(scrape_date);
CREATE INDEX IF NOT EXISTS idx_anomalies_product_key ON gold.price_anomalies(product_key);

-- Operational Price Anomalies Mart
CREATE TABLE IF NOT EXISTS gold.mart_price_anomalies (
    id BIGSERIAL PRIMARY KEY,
    scrape_date DATE NOT NULL,
    item_id VARCHAR(128),
    product_key VARCHAR(128) NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    canonical_name TEXT,
    coicop_division VARCHAR(16),
    price_khr NUMERIC(14, 2) NOT NULL,
    expected_price_khr NUMERIC(14, 2) NOT NULL,
    pct_change NUMERIC(6, 2) NOT NULL,
    anomaly_type VARCHAR(16) NOT NULL,
    root_cause_flag VARCHAR(32) NOT NULL DEFAULT 'UNSPECIFIED',
    is_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Historical Official NIS Monthly CPI Records for Ground-Truth Benchmarking
CREATE TABLE IF NOT EXISTS gold.dim_nis_official_cpi (
    cpi_month DATE NOT NULL PRIMARY KEY,
    headline_cpi NUMERIC(10, 4) NOT NULL,
    core_cpi NUMERIC(10, 4),
    mom_inflation_pct NUMERIC(8, 4),
    yoy_inflation_pct NUMERIC(8, 4),
    release_date DATE,
    source_notes TEXT DEFAULT 'NIS Cambodia Official CPI Release',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Machine Learning-Assisted Daily Inflation Nowcasting Mart
CREATE TABLE IF NOT EXISTS gold.fct_cpi_nowcast (
    nowcast_date DATE NOT NULL,
    target_month DATE NOT NULL,
    days_observed INTEGER NOT NULL,
    days_remaining INTEGER NOT NULL,
    days_in_month INTEGER NOT NULL,
    realized_cpi_so_far NUMERIC(10, 4),
    projected_remaining_cpi NUMERIC(10, 4),
    projected_mom_pct NUMERIC(8, 4) NOT NULL,
    nowcast_headline_cpi NUMERIC(10, 4) NOT NULL,
    nowcast_nis_headline_cpi NUMERIC(10, 4),
    nowcast_core_cpi NUMERIC(10, 4),
    prior_month_cpi NUMERIC(10, 4),
    ci_lower_95 NUMERIC(10, 4),
    ci_upper_95 NUMERIC(10, 4),
    uncertainty_pct NUMERIC(6, 3),
    model_name VARCHAR(50) DEFAULT 'ml_assisted_nowcaster_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (nowcast_date, target_month, model_name)
);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_nowcast_target_month ON gold.fct_cpi_nowcast(target_month);
CREATE INDEX IF NOT EXISTS idx_fct_cpi_nowcast_date ON gold.fct_cpi_nowcast(nowcast_date);

-- Performance Indexes for Silver Fact & Bronze Tables
-- Performance Indexes for Gold Fact & Dimensions, Silver Store Prices, and Bronze Tables
CREATE INDEX IF NOT EXISTS idx_fct_daily_prices_date_item ON gold.fct_daily_prices(scrape_date, item_id);
CREATE INDEX IF NOT EXISTS idx_fct_daily_prices_item_store_date ON gold.fct_daily_prices(item_id, store_slug, scrape_date);
CREATE INDEX IF NOT EXISTS idx_fct_daily_prices_scrape_date ON gold.fct_daily_prices(scrape_date);
CREATE INDEX IF NOT EXISTS idx_fct_daily_prices_store_item ON gold.fct_daily_prices(store_slug, item_id);
CREATE INDEX IF NOT EXISTS idx_gold_dim_items_id ON gold.dim_items(item_id);
CREATE INDEX IF NOT EXISTS idx_silver_clean_store_prices_store_date ON silver.clean_store_prices(store_slug, scrape_date);
CREATE INDEX IF NOT EXISTS idx_silver_clean_store_prices_item ON silver.clean_store_prices(item_id);
CREATE INDEX IF NOT EXISTS idx_raw_prices_scraped_at ON bronze.raw_prices(scraped_at);
CREATE INDEX IF NOT EXISTS idx_item_match_log_raw_price ON silver.item_match_log(raw_price_id);
CREATE INDEX IF NOT EXISTS idx_canonical_items_name ON silver.canonical_items(canonical_name);
CREATE INDEX IF NOT EXISTS idx_canonical_items_lower_trim ON silver.canonical_items (lower(trim(canonical_name)));

-- ============================================================================
-- SEED DATA: OFFICIAL CAMBODIA NIS COICOP WEIGHTS & AEON CATEGORY MAP
-- ============================================================================

INSERT INTO gold.coicop_weights (coicop_division, division_name, weight_pct, source, effective_date)
VALUES
    ('01', 'Food and non-alcoholic beverages', 44.800, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('02', 'Alcoholic beverages, tobacco and narcotics', 1.500, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('03', 'Clothing and footwear', 2.900, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('04', 'Housing, water, electricity, gas and other fuels', 17.100, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('05', 'Furnishings, household equipment and routine household maintenance', 3.300, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('06', 'Health', 5.600, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('07', 'Transport', 12.200, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('08', 'Communication', 3.900, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('09', 'Recreation and culture', 1.900, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('10', 'Education', 1.500, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('11', 'Restaurants and hotels', 3.100, 'NIS Cambodia Official Basket', '2026-08-01'),
    ('12', 'Miscellaneous goods and services', 2.200, 'NIS Cambodia Official Basket', '2026-08-01')
ON CONFLICT (coicop_division) DO UPDATE 
SET weight_pct = EXCLUDED.weight_pct,
    division_name = EXCLUDED.division_name;

-- Seed AEON Starter Category Map (30 Food categories)
INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
VALUES
    ('aeon', '125', '01'), ('aeon', '20', '01'), ('aeon', '29', '01'), ('aeon', '47', '01'),
    ('aeon', '23', '01'), ('aeon', '28', '01'), ('aeon', '55', '01'), ('aeon', '27', '01'),
    ('aeon', '32', '01'), ('aeon', '42', '01'), ('aeon', '50', '01'), ('aeon', '52', '01'),
    ('aeon', '41', '01'), ('aeon', '40', '01'), ('aeon', '33', '01'), ('aeon', '14', '01'),
    ('aeon', '6', '01'),  ('aeon', '107', '01'), ('aeon', '111', '01'), ('aeon', '185', '01'),
    ('aeon', '187', '01'), ('aeon', '188', '01'), ('aeon', '190', '01'), ('aeon', '196', '01'),
    ('aeon', '209', '01'), ('aeon', '218', '01'), ('aeon', '219', '01'), ('aeon', '404', '01'),
    ('aeon', '503', '01'), ('aeon', '533', '01')
ON CONFLICT (store_slug, category_native) DO UPDATE
SET coicop_division = EXCLUDED.coicop_division;

-- Helpful Indexes for high performance dbt execution
CREATE INDEX IF NOT EXISTS idx_coicop_cat_map_lookup ON silver.coicop_category_map (store_slug, lower(category_native));
CREATE INDEX IF NOT EXISTS idx_dim_coicop_ai_cache_lower_name ON silver.dim_coicop_ai_cache (lower(product_name));
CREATE INDEX IF NOT EXISTS idx_dim_coicop_ai_cache_coicop_code ON silver.dim_coicop_ai_cache (coicop_code);

-- Seed AEON Stationery categories -> Recreation & Culture / Stationery (Division 09, UN COICOP 09.5.4)
INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
VALUES
    ('aeon', 'Stationery', '09'), ('aeon', 'School Supplies', '09'), ('aeon', 'Books', '09'),
    ('aeon', 'Notebooks', '09'), ('aeon', 'Pens & Pencils', '09'), ('aeon', 'Art & Craft', '09')
ON CONFLICT (store_slug, category_native) DO UPDATE
SET coicop_division = EXCLUDED.coicop_division;

-- Seed Khmer Samnang Phone Shop category mappings
INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
VALUES
    ('samnangshop', 'Smartphones', '08'),
    ('samnangshop', 'Apple > iPhone > Smartphones', '08'),
    ('samnangshop', 'Samsung > Galaxy S > Smartphones', '08'),
    ('samnangshop', 'Xiaomi > Flagship > Smartphones', '08'),
    ('samnangshop', 'Apple > iPad > Tablets', '08'),
    ('samnangshop', 'Apple > Watch > Wearables', '12'),
    ('samnangshop', 'Apple > Audio > Accessories', '09'),
    ('samnangshop', 'Accessories', '08')
ON CONFLICT (store_slug, category_native) DO UPDATE
SET coicop_division = EXCLUDED.coicop_division;

-- Seed redBus Cambodia category mappings -> Transport (Division 07)
INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
VALUES
    ('redbus', 'Intercity Bus > Passenger Transport by Road', '07'),
    ('redbus', 'Intercity Bus', '07'),
    ('redbus', 'Passenger Transport by Road', '07')
ON CONFLICT (store_slug, category_native) DO UPDATE
SET coicop_division = EXCLUDED.coicop_division;

-- Seed BookMeBus Cambodia category mappings -> Transport (Division 07)
INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
VALUES
    ('bookmebus', 'Intercity Bus > Passenger Transport by Road', '07'),
    ('bookmebus', 'Intercity Bus', '07'),
    ('bookmebus', 'Passenger Transport by Road', '07')
ON CONFLICT (store_slug, category_native) DO UPDATE
SET coicop_division = EXCLUDED.coicop_division;

-- Seed Delishop and Aeon Pet category mappings -> Recreation and culture (Division 09, COICOP 09.3.4)
INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
VALUES
    ('delishop', 'Pets > Cat & Dog Baby Milk', '09'),
    ('delishop', 'Pets > Cat Food', '09'),
    ('delishop', 'Pets > Cat Toys', '09'),
    ('delishop', 'Pets > Dog Food', '09'),
    ('delishop', 'Pets > Dog Toys', '09'),
    ('delishop', 'Pets > Kitten', '09'),
    ('delishop', 'Pets > Litter', '09'),
    ('delishop', 'Pets > Medications', '09'),
    ('delishop', 'Pets > Other Pets', '09'),
    ('delishop', 'Pets > Pet toileteries', '09'),
    ('delishop', 'Pets > Pets Accessories', '09'),
    ('delishop', 'Pets > Puppy', '09'),
    ('delishop', 'Pets > Travel Crate', '09'),
    ('delishop', 'Pets > Treats', '09'),
    ('delishop', 'Pets', '09'),
    -- Delishop full root category taxonomy
    ('delishop', 'Pantry', '01'),
    ('delishop', 'Sweet Corner', '01'),
    ('delishop', 'Coffee & Tea', '01'),
    ('delishop', 'Dairy Products', '01'),
    ('delishop', 'Baking', '01'),
    ('delishop', 'Meat & Poultry', '01'),
    ('delishop', 'Vegetables & Fruits', '01'),
    ('delishop', 'Breakfast', '01'),
    ('delishop', 'Fruit Drinks', '01'),
    ('delishop', 'Ready Meal & Caterer', '01'),
    ('delishop', 'Soda', '01'),
    ('delishop', 'Seafood', '01'),
    ('delishop', 'Milk', '01'),
    ('delishop', 'Water', '01'),
    ('delishop', 'Wine', '02'),
    ('delishop', 'Spirit', '02'),
    ('delishop', 'Beer & Cider', '02'),
    ('delishop', 'Homewares & Accessories > Tobacco & Accessories', '02'),
    ('delishop', 'Tobacco & Accessories', '02'),
    ('delishop', 'Homewares & Accessories', '05'),
    ('delishop', 'Household Essentials', '05'),
    ('delishop', 'Tableware', '05'),
    ('delishop', 'Pharmacy & Parapharmacy', '06'),
    ('delishop', 'Nutrition Product', '06'),
    ('delishop', 'Electronic & Computer', '08'),
    ('delishop', 'Games & Toys', '09'),
    ('delishop', 'Stationery', '09'),
    ('delishop', 'Personal Care', '12'),
    ('delishop', 'Baby''s World', '12'),
    ('delishop', 'Baby Care', '12'),
    ('delishop', 'Cosmetics & Make-Up', '12'),
    ('delishop', 'Jewelry', '12'),
    ('aeon', 'Pet Food', '09'),
    ('aeon', 'Pet Care', '09'),
    ('aeon', 'Pet Accessories', '09'),
    ('aeon', 'Dog Food', '09'),
    ('aeon', 'Cat Food', '09')
ON CONFLICT (store_slug, category_native) DO UPDATE
SET coicop_division = EXCLUDED.coicop_division;

-- Seed comprehensive AEON 1 & AEON 3 Category Taxonomy Mappings
INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
VALUES
    -- Division 02: Alcoholic beverages & tobacco
    ('aeon', 'Grocery > Beer', '02'), ('aeon', 'Beer', '02'),
    ('aeon', 'Grocery > Wine', '02'), ('aeon', 'Wine', '02'),
    ('aeon', 'Grocery > Hard Liquor', '02'), ('aeon', 'Hard Liquor', '02'),
    ('aeon', 'Grocery > Cigarette', '02'), ('aeon', 'Cigarette', '02'), ('aeon', 'Cigarettes', '02'),
    ('aeon', 'TopValu > Beverage & Liquor', '02'), ('aeon', 'Organic > Beverage & Liquor', '02'),
    ('aeon', 'Beverage & Liquor', '02'), ('aeon', 'Liquor', '02'), ('aeon', 'Wine & Spirits', '02'),
    ('aeon3', 'Grocery > Beer', '02'), ('aeon3', 'Beer', '02'),
    ('aeon3', 'Grocery > Wine', '02'), ('aeon3', 'Wine', '02'),
    ('aeon3', 'Grocery > Hard Liquor', '02'), ('aeon3', 'Hard Liquor', '02'),
    ('aeon3', 'Grocery > Cigarette', '02'), ('aeon3', 'Cigarette', '02'), ('aeon3', 'Cigarettes', '02'),
    ('aeon3', 'TopValu > Beverage & Liquor', '02'), ('aeon3', 'Organic > Beverage & Liquor', '02'),

    -- Division 03: Clothing and footwear
    ('aeon', 'Apparel', '03'), ('aeon', 'Clothing', '03'), ('aeon', 'Fashion', '03'),
    ('aeon', 'Kids > Boy Apparel', '03'), ('aeon', 'Kids > Girl Apparel', '03'),
    ('aeon', 'Kids > TopValu Kids Boys', '03'), ('aeon', 'Kids > TopValu Kids Girls', '03'),
    ('aeon', 'Kids > Children Homewear', '03'), ('aeon', 'Kids > Boy Shoes', '03'),
    ('aeon', 'Kids > Girls Shoes', '03'), ('aeon', 'Shoes', '03'), ('aeon', 'Footwear', '03'),
    ('aeon', 'Men Apparel', '03'), ('aeon', 'Women Apparel', '03'), ('aeon', 'Kids Apparel', '03'),
    ('aeon3', 'Apparel', '03'), ('aeon3', 'Clothing', '03'), ('aeon3', 'Fashion', '03'),
    ('aeon3', 'Kids > Boy Apparel', '03'), ('aeon3', 'Kids > Girl Apparel', '03'),

    -- Division 05: Furnishings, household equipment & maintenance
    ('aeon', 'Household', '05'), ('aeon', 'Household > Dining', '05'), ('aeon', 'Household > Kitchen', '05'),
    ('aeon', 'Home Coordy', '05'), ('aeon', 'Home Coordy > Bedding', '05'), ('aeon', 'Home Coordy > Bath Essential', '05'),
    ('aeon', 'Home Coordy > Interior Living', '05'), ('aeon', 'Home Coordy > Interior Dining & Kitchen', '05'),
    ('aeon', 'Home Coordy > Home Furniture', '05'), ('aeon', 'Home Coordy > Home Storage', '05'),
    ('aeon', 'Home Coordy > Dining Goods', '05'), ('aeon', 'Home Coordy > Kitchen Goods', '05'),
    ('aeon', 'Home Coordy > Laundry & Cleaning', '05'), ('aeon', 'Home Coordy > Sports Goods', '05'),
    ('aeon', 'Health & Hygiene > Cleaning liquid', '05'), ('aeon', 'Cleaning liquid', '05'),
    ('aeon', 'Laundry', '05'), ('aeon', 'Detergent', '05'),
    ('aeon', 'D.I.Y', '05'), ('aeon', 'D.I.Y > DIY & Accessories', '05'), ('aeon', 'D.I.Y > Batteries', '05'),
    ('aeon', 'D.I.Y > Car Care & Accessories', '05'), ('aeon', 'D.I.Y > Motor Cycle Care & Accessories', '05'),
    ('aeon', 'D.I.Y > Gardening Goods', '05'), ('aeon', 'D.I.Y > Fresh Flower & Plants', '05'),
    ('aeon', 'Daiso', '05'), ('aeon', 'Daiso > Home & Lifestyle', '05'),
    ('aeon', 'Home Fashion', '05'), ('aeon', 'Home Fashion > Bath Essential', '05'),
    ('aeon', 'Home Fashion > Towel', '05'), ('aeon', 'Home Fashion > Interior Living', '05'),
    ('aeon', 'Home Fashion > Interior Decoration', '05'), ('aeon', 'Home Fashion > Interior, Dining & Kitchen', '05'),
    ('aeon', 'Home Fashion > Home Storage', '05'), ('aeon', 'Home Fashion > Living Room', '05'),
    ('aeon', 'Home Fashion > Bedding & Accessories', '05'), ('aeon', 'Home Fashion > Praying Goods', '05'),
    ('aeon', 'Electrical & Multimedia > Small Appliance', '05'), ('aeon', 'Electrical & Multimedia > Large Appliance', '05'),
    ('aeon', 'Electrical & Multimedia > Air Conditioner, Fan & Purifier', '05'),
    ('aeon', 'TopValu > Non-food', '05'),
    ('aeon3', 'Household', '05'), ('aeon3', 'Health & Hygiene > Cleaning liquid', '05'),
    ('aeon3', 'Home Coordy', '05'), ('aeon3', 'Daiso', '05'),

    -- Division 06: Health
    ('aeon', 'Health & Hygiene > Health Support', '06'), ('aeon', 'Health Support', '06'),
    ('aeon', 'Medicine', '06'), ('aeon', 'Pharmacy', '06'), ('aeon', 'First Aid', '06'),
    ('aeon3', 'Health & Hygiene > Health Support', '06'), ('aeon3', 'Health Support', '06'),

    -- Division 08: Communication
    ('aeon', 'Electrical & Multimedia > Smartphone', '08'),
    ('aeon', 'Electrical & Multimedia > Mobile Phones Accessories', '08'),
    ('aeon', 'Daiso > Technology & Personal Essentials', '08'),
    ('aeon', 'Smartphone', '08'), ('aeon', 'Mobile Phones Accessories', '08'),

    -- Division 09: Recreation and culture
    ('aeon', 'Health & Hygiene > Pet Care', '09'),
    ('aeon', 'Stationery > School', '09'), ('aeon', 'Stationery > Office', '09'),
    ('aeon', 'Stationery > iRASHIKU School', '09'), ('aeon', 'Stationery > Fancy', '09'),
    ('aeon', 'Stationery > iR Home', '09'),
    ('aeon', 'Toys', '09'), ('aeon', 'Toys > Vehicle Playsets', '09'), ('aeon', 'Toys > Animal Figures', '09'),
    ('aeon', 'Toys > Soft Toys', '09'), ('aeon', 'Toys > Toys and Me', '09'), ('aeon', 'Toys > ZURU Toys', '09'),
    ('aeon', 'Sports', '09'), ('aeon', 'Sports > Equipment & Accessories', '09'),
    ('aeon', 'Electrical & Multimedia > Audio', '09'), ('aeon', 'Electrical & Multimedia > Visual', '09'),
    ('aeon3', 'Health & Hygiene > Pet Care', '09'), ('aeon3', 'Toys', '09'), ('aeon3', 'Sports', '09'),

    -- Division 12: Miscellaneous personal care
    ('aeon', 'Health & Hygiene', '12'), ('aeon', 'Health & Hygiene > Sanitary', '12'),
    ('aeon', 'Health & Hygiene > Cleaning Goods', '12'), ('aeon', 'Health & Hygiene > Personal Care', '12'),
    ('aeon', 'Health & Hygiene > Skin Care', '12'), ('aeon', 'Health & Hygiene > Grooming', '12'),
    ('aeon', 'Khmer Products > Local Hygiene', '12'),
    ('aeon', 'Baby', '12'), ('aeon', 'Baby > Baby Products', '12'), ('aeon', 'Baby > Baby Care', '12'),
    ('aeon', 'Baby > Toilet & Laundry', '12'), ('aeon', 'Baby > Baby Outdoor', '12'),
    ('aeon', 'Sanitary', '12'), ('aeon', 'Personal Care', '12'), ('aeon', 'Skin Care', '12'),
    ('aeon', 'Grooming', '12'), ('aeon', 'Cosmetics', '12'),
    ('aeon', 'Kids > Boy Bags', '12'), ('aeon', 'Kids > Girl Bags', '12'), ('aeon', 'Kids > Kids Accessories', '12'),
    ('aeon3', 'Health & Hygiene', '12'), ('aeon3', 'Baby', '12'),

    -- Division 01: Food and non-alcoholic beverages
    ('aeon', 'Perishable', '01'), ('aeon', 'Daily & Dairy', '01'), ('aeon', 'Ready to Eat', '01'),
    ('aeon', 'Organic', '01'), ('aeon', 'Khmer Products', '01'), ('aeon', 'TopValu', '01'),
    ('aeon', 'Grocery', '01'), ('aeon', 'Baby > Baby Feeding', '01'),
    ('aeon3', 'Perishable', '01'), ('aeon3', 'Daily & Dairy', '01'), ('aeon3', 'Ready to Eat', '01'),
    ('aeon3', 'Organic', '01'), ('aeon3', 'Khmer Products', '01'), ('aeon3', 'TopValu', '01'),
    ('aeon3', 'Grocery', '01')
ON CONFLICT (store_slug, category_native) DO UPDATE
SET coicop_division = EXCLUDED.coicop_division;




