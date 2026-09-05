-- ============================================================================
-- 011 — Remove dead objects + add a DB-level dedup backstop for bronze
-- ============================================================================
-- Follow-up to the audit fixes:
--
-- 1. staging.stg_item_mapping had no writer since pipeline/canonicalizer.py
--    was removed (only migration 006 seeded it). Both remaining consumers
--    (Gemini classifier persist step, hedonic regression) have been repointed;
--    nothing reads it anymore -> drop it.
-- 2. staging.raw_scrapes.is_processed was never set or read by any code ->
--    drop the column (its partial index goes with it).
-- 3. bronze.raw_prices dedup was application-side only; add a unique index
--    matching the scraper's re-scrape key so parallel/racing DAG runs cannot
--    double-ingest. Clean up existing duplicates first, keeping the lowest id.

BEGIN;

-- 1. Dead mapping table (indexes drop with it).
DROP TABLE IF EXISTS staging.stg_item_mapping;

-- 2. Dead flag column.
DROP INDEX IF EXISTS idx_raw_scrapes_unprocessed;
ALTER TABLE staging.raw_scrapes DROP COLUMN IF EXISTS is_processed;

-- 3. Deduplicate bronze observations, then enforce uniqueness.
DELETE FROM bronze.raw_prices a
USING bronze.raw_prices b
WHERE a.raw_price_id > b.raw_price_id
  AND a.store_id IS NOT DISTINCT FROM b.store_id
  AND a.source_name IS NOT DISTINCT FROM b.source_name
  AND COALESCE(a.source_url, '') = COALESCE(b.source_url, '')
  AND a.item_description_raw = b.item_description_raw
  AND a.price = b.price
  AND (a.scraped_at AT TIME ZONE 'UTC')::date
    = (b.scraped_at AT TIME ZONE 'UTC')::date;

CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_prices_observation
    ON bronze.raw_prices (
        store_id, source_name,
        COALESCE(source_url, ''), item_description_raw, price,
        (scraped_at AT TIME ZONE 'UTC')::date
    );

COMMIT;
