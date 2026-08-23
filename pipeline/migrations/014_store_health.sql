-- 014: Store health metadata views ("metadata base") powering the per-store
-- dashboards + volume guardrail alerts.
--
-- Detects source-side truncation like the 2026-08-22 delishop incident where
-- the morning crawl captured 5,800 products instead of the usual ~21K while
-- the scraper itself reported SUCCESS.
--
--   gold.v_store_health_daily   : one row per (store_slug, scrape_date) with
--                                 volume vs trailing-7-day baseline + status
--   gold.v_store_health_latest  : most recent row per store (alert surface)
--   gold.v_store_dashboard      : one overview row per store for dashboards
--
-- Status thresholds (vs trailing 7-day baseline of PRIOR days only):
--   OK            within normal variance
--   WARNING_LOW   below 70% of baseline
--   CRITICAL_DROP below 50% of baseline  <- page someone
--   NO_DATA       zero records on the day
--   NEW           no baseline yet (<2 days of history)

CREATE OR REPLACE VIEW gold.v_store_health_daily AS
WITH daily AS (
    SELECT
        store_id AS store_slug,
        scraped_at::date AS scrape_date,
        count(*)::int AS records_scraped
    FROM bronze.raw_prices
    GROUP BY 1, 2
)
SELECT
    d.store_slug,
    d.scrape_date,
    d.records_scraped,
    round(b.baseline_7d::numeric, 0)::int AS baseline_7d,
    CASE
        WHEN b.baseline_7d IS NULL OR b.baseline_7d = 0 THEN NULL
        ELSE round((((d.records_scraped - b.baseline_7d) / b.baseline_7d) * 100)::numeric, 1)
    END AS pct_vs_baseline,
    CASE
        WHEN b.baseline_7d IS NULL OR b.baseline_7d = 0 THEN 'NEW'
        WHEN d.records_scraped <= 0 THEN 'NO_DATA'
        WHEN d.records_scraped < b.baseline_7d * 0.5 THEN 'CRITICAL_DROP'
        WHEN d.records_scraped < b.baseline_7d * 0.7 THEN 'WARNING_LOW'
        ELSE 'OK'
    END AS health_status
FROM daily d
LEFT JOIN LATERAL (
    SELECT avg(x.records_scraped) AS baseline_7d
    FROM daily x
    WHERE x.store_slug = d.store_slug
      AND x.scrape_date >= d.scrape_date - INTERVAL '7 days'
      AND x.scrape_date < d.scrape_date
) b ON true;

CREATE OR REPLACE VIEW gold.v_store_health_latest AS
SELECT DISTINCT ON (store_slug)
    store_slug, scrape_date, records_scraped, baseline_7d, pct_vs_baseline, health_status
FROM gold.v_store_health_daily
ORDER BY store_slug, scrape_date DESC;

CREATE OR REPLACE VIEW gold.v_store_dashboard AS
WITH stores AS (
    SELECT DISTINCT store_id AS store_slug FROM bronze.raw_prices
),
agg AS (
    SELECT
        store_id AS store_slug,
        count(*) AS total_records,
        count(DISTINCT item_description_raw) AS distinct_items,
        min(scraped_at) AS first_scraped_at,
        max(scraped_at) AS last_scraped_at
    FROM bronze.raw_prices
    GROUP BY 1
)
SELECT
    s.store_slug,
    a.distinct_items,
    a.total_records,
    a.first_scraped_at,
    a.last_scraped_at,
    now() - a.last_scraped_at AS freshness_age,
    h.scrape_date AS latest_scrape_date,
    h.records_scraped AS latest_day_records,
    h.baseline_7d,
    h.pct_vs_baseline,
    h.health_status
FROM stores s
JOIN agg a ON a.store_slug = s.store_slug
LEFT JOIN gold.v_store_health_latest h ON h.store_slug = s.store_slug;
