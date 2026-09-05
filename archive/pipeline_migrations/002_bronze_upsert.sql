-- =============================================================================
-- CAMBODIA CPI PIPELINE — MIGRATION 002: BRONZE STAGING UPSERT & DEDUPLICATION
-- =============================================================================
-- Purpose:
--   Enforce ONE row per (scrape_date, store_slug) in staging.raw_scrapes.
--   - Same-day re-scrapes overwrite / update the existing day's row.
--   - New scrape dates append normally.
--   - Existing multi-scrape duplicates are deduped to the latest row.
--
-- Idempotency:
--   Can be executed repeatedly without errors or data corruption.
-- =============================================================================

-- Step 1: Ensure table structure exists and preserves all required columns
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.raw_scrapes (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    scrape_date DATE NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    record_count INT NOT NULL DEFAULT 0,
    payload JSONB,
    raw_json JSONB,
    is_processed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ensure raw_json column exists and payload constraint is relaxed if pre-existing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'staging' AND table_name = 'raw_scrapes' AND column_name = 'raw_json'
    ) THEN
        ALTER TABLE staging.raw_scrapes ADD COLUMN raw_json JSONB;
    END IF;
    
    -- Sync existing payload to raw_json if raw_json is null
    UPDATE staging.raw_scrapes SET raw_json = payload WHERE raw_json IS NULL AND payload IS NOT NULL;
END $$;

-- Step 2: Deduplicate existing data — keep the LATEST row per (scrape_date, store_slug)
DELETE FROM staging.raw_scrapes
WHERE id NOT IN (
    SELECT DISTINCT ON (scrape_date, store_slug) id
    FROM staging.raw_scrapes
    ORDER BY scrape_date, store_slug, created_at DESC, id DESC
);

-- Step 3: Create Unique Index for (scrape_date, store_slug) if not exists
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_scrapes_day_store
    ON staging.raw_scrapes (scrape_date, store_slug);

-- Step 4: Verification DO block — Raises EXCEPTION if duplicate rule is violated
DO $$
DECLARE
    v_duplicate_groups INT;
BEGIN
    SELECT COUNT(*)
    INTO v_duplicate_groups
    FROM (
        SELECT scrape_date, store_slug, COUNT(*)
        FROM staging.raw_scrapes
        GROUP BY scrape_date, store_slug
        HAVING COUNT(*) > 1
    ) dupes;

    IF v_duplicate_groups > 0 THEN
        RAISE EXCEPTION 'Verification Failed: % duplicate (scrape_date, store_slug) groups found in staging.raw_scrapes!', v_duplicate_groups;
    END IF;

    RAISE NOTICE 'Verification Passed: staging.raw_scrapes has 0 duplicates across (scrape_date, store_slug). Unique index uq_raw_scrapes_day_store is active.';
END $$;

-- =============================================================================
-- Verification Queries (Run manually or via psql):
-- =============================================================================

-- Verification Query 1: Duplicate check (must return 0 rows)
-- SELECT scrape_date, store_slug, count(*)
-- FROM staging.raw_scrapes
-- GROUP BY 1, 2
-- HAVING count(*) > 1;

-- Verification Query 2: Per-day summary (date, store count, total items)
-- SELECT scrape_date, COUNT(DISTINCT store_slug) AS store_count, SUM(record_count) AS total_items
-- FROM staging.raw_scrapes
-- GROUP BY scrape_date
-- ORDER BY scrape_date DESC;
