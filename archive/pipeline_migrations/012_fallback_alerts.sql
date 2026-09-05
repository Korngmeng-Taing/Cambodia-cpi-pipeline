-- =============================================================================
-- 012_fallback_alerts.sql
-- Fallback observability (Risk 3): baseline-only scrapers silently inflate
-- is_fallback rows when live fetches fail. This table persists one row per
-- (scrape_date, store_slug) with the fallback ratio so Metabase can trend it
-- and alert when a source's live feed has been down too long.
--
-- Written by pipeline/bronze_ingestion.py:ingest_source_bronze after each
-- batch lands in bronze.raw_prices.
--
-- Suggested Metabase cards:
--   * Latest-day fallback ratio by source:
--       SELECT store_slug, fallback_rows, total_rows, fallback_ratio
--       FROM staging.fallback_alerts
--       WHERE scrape_date = (SELECT max(scrape_date) FROM staging.fallback_alerts)
--       ORDER BY fallback_ratio DESC;
--   * Alert condition: fallback_ratio > 0.5 for any source on the latest day
--     (long live outage producing zero real observations).
--
-- Idempotent: safe to re-run. Applied to the running DB with:
--   psql -U cpi_user -d cpi_db -f pipeline/migrations/012_fallback_alerts.sql
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.fallback_alerts (
    scrape_date DATE NOT NULL,
    store_slug VARCHAR(64) NOT NULL,
    fallback_rows INT NOT NULL,
    total_rows INT NOT NULL,
    fallback_ratio NUMERIC(5,4) GENERATED ALWAYS AS
        (fallback_rows::numeric / NULLIF(total_rows, 0)) STORED,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (scrape_date, store_slug)
);

CREATE INDEX IF NOT EXISTS idx_fallback_alerts_store_date
    ON staging.fallback_alerts(store_slug, scrape_date DESC);
