-- =============================================================================
-- Migration 018: Audit Remediation Fixes
-- Date: 2026-09-06
-- Description:
--   1. Drop and recreate bronze.uq_raw_prices_observation without price column
--      to guarantee at most 1 observation per item, per store, per day.
--   2. Update gold.v_monitor_price_alerts to use LAG() window function instead
--      of strict 1-day interval join to handle weekend/multi-day gaps.
-- =============================================================================

-- 1. Update Bronze observation unique index
DROP INDEX IF EXISTS bronze.uq_raw_prices_observation;
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_prices_observation
    ON bronze.raw_prices (
        store_id, source_name,
        COALESCE(source_url, ''), item_description_raw,
        ((scraped_at AT TIME ZONE 'UTC')::date)
    );

-- 2. Recreate gold.v_monitor_price_alerts view with LAG() window function
CREATE OR REPLACE VIEW gold.v_monitor_price_alerts AS
WITH price_with_prev AS (
    SELECT
        scrape_date,
        store_slug,
        item_id,
        price_khr,
        LAG(price_khr) OVER (PARTITION BY store_slug, item_id ORDER BY scrape_date) AS prev_price_khr
    FROM gold.fct_daily_prices
    WHERE price_khr > 0
)
SELECT
    curr.scrape_date,
    curr.store_slug,
    curr.item_id,
    m.canonical_name AS name_clean,
    m.coicop_division,
    curr.prev_price_khr AS yesterday_price_khr,
    curr.price_khr AS today_price_khr,
    ROUND((curr.price_khr - curr.prev_price_khr) / NULLIF(curr.prev_price_khr, 0) * 100.0, 2) AS dod_price_change_pct,
    CASE
        WHEN curr.price_khr > curr.prev_price_khr * 2.0 THEN 'CRITICAL_SPIKE (+100%)'
        WHEN curr.price_khr > curr.prev_price_khr * 1.3 THEN 'HIGH_SURGE (+30%)'
        WHEN curr.price_khr < curr.prev_price_khr * 0.5 THEN 'CRITICAL_DROP (-50%)'
        WHEN curr.price_khr < curr.prev_price_khr * 0.7 THEN 'HIGH_DROP (-30%)'
        ELSE 'MODERATE_SHIFT'
    END AS alert_level
FROM price_with_prev curr
LEFT JOIN gold.dim_items m ON m.item_id = curr.item_id
WHERE curr.prev_price_khr IS NOT NULL
  AND curr.prev_price_khr > 0
  AND ABS(curr.price_khr - curr.prev_price_khr) / curr.prev_price_khr >= 0.20
ORDER BY curr.scrape_date DESC, ABS((curr.price_khr - curr.prev_price_khr) / curr.prev_price_khr) DESC;
