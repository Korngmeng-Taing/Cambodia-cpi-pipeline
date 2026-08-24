-- ============================================================================
-- CAMBODIA CPI PIPELINE — OPERATIONS & MONITORING SERVING VIEWS
-- Sourced from silver.fct_daily_prices, silver.dim_items, gold.coicop_weights,
-- and staging.exchange_rates.
-- ============================================================================


-- 5. View: Data Coverage and Pipeline Audit
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
ORDER BY d.scrape_date DESC, d.store_slug;


-- ============================================================================
-- 9. View: Observed-Only Inflation (excludes LOCF-imputed rows from change calcs)
-- DoD/MoM inflation computed on actually-observed quotes only, so forward-carried
-- prices (is_imputed=TRUE) cannot smooth or zero out real price moves.
-- ============================================================================
CREATE OR REPLACE VIEW gold.v_inflation_observed AS
WITH observed_stats AS (
    SELECT scrape_date, item_id, coicop_division, p_khr_jevons
    FROM gold.fct_daily_price_stats
    WHERE is_imputed = FALSE
      AND p_khr_jevons > 0
),
base AS (
    SELECT product_key AS item_id, base_price_khr
    FROM gold.base_prices
    WHERE base_period = (SELECT MAX(base_period) FROM gold.base_prices)
),
cat AS (
    SELECT
        s.scrape_date,
        s.coicop_division,
        ROUND(EXP(AVG(LN(s.p_khr_jevons / b.base_price_khr))) * 100.0, 4) AS index_value
    FROM observed_stats s
    JOIN base b ON b.item_id = s.item_id
    WHERE b.base_price_khr > 0
    GROUP BY s.scrape_date, s.coicop_division
),
cat_w AS (
    SELECT c.scrape_date, c.coicop_division, c.index_value, w.weight_pct
    FROM cat c
    JOIN gold.coicop_weights w ON w.coicop_division = c.coicop_division
),
tot AS (
    SELECT scrape_date, SUM(weight_pct) AS total_weight, COUNT(*) AS divisions_present
    FROM cat_w
    GROUP BY scrape_date
),
headline AS (
    SELECT
        c.scrape_date,
        ROUND(SUM(c.index_value * (c.weight_pct / NULLIF(t.total_weight, 0))), 4) AS cpi_observed,
        t.divisions_present
    FROM cat_w c
    JOIN tot t ON t.scrape_date = c.scrape_date
    WHERE t.total_weight > 0
    GROUP BY c.scrape_date, t.divisions_present
)
SELECT
    h.scrape_date,
    h.cpi_observed,
    h.divisions_present,
    ROUND((h.cpi_observed - prev.cpi_observed) / NULLIF(prev.cpi_observed, 0) * 100.0, 3) AS dod_inflation_pct_observed
FROM headline h
LEFT JOIN headline prev
    ON prev.scrape_date = (h.scrape_date - INTERVAL '1 day')::DATE
ORDER BY h.scrape_date DESC;


-- ============================================================================
-- 10. METABASE SCRAPER OBSERVABILITY & MONITORING DASHBOARD VIEWS
-- ============================================================================
-- 10.1 Daily Scraper Operational Health Dashboard (Real-Time Bronze Ingestion)
CREATE OR REPLACE VIEW gold.v_monitor_scraper_daily AS
SELECT
    r.scrape_date,
    r.store_slug,
    r.record_count::BIGINT AS total_items_scraped,
    COALESCE(s.unique_items, r.record_count)::BIGINT AS unique_items,
    s.avg_price_khr,
    s.min_price_khr,
    s.max_price_khr,
    COALESCE(s.promo_count, 0)::BIGINT AS promo_count,
    COALESCE(s.promo_pct, 0.0) AS promo_pct,
    COALESCE(s.fallback_count, 0)::BIGINT AS fallback_count,
    COALESCE(s.fallback_pct, 0.0) AS fallback_pct,
    COALESCE(s.outlier_count, 0)::BIGINT AS outlier_count,
    r.created_at AS last_scraped_at,
    CASE
        WHEN r.record_count = 0 THEN 'EMPTY_WARNING'
        WHEN s.fallback_pct > 50.0 THEN 'FALLBACK_ACTIVE'
        ELSE 'HEALTHY'
    END AS operational_status
FROM staging.raw_scrapes r
LEFT JOIN (
    SELECT
        scrape_date,
        store_slug,
        COUNT(DISTINCT item_id) AS unique_items,
        ROUND(AVG(price_khr), 2) AS avg_price_khr,
        ROUND(MIN(price_khr), 2) AS min_price_khr,
        ROUND(MAX(price_khr), 2) AS max_price_khr,
        COUNT(*) FILTER (WHERE on_promo = TRUE) AS promo_count,
        ROUND(COUNT(*) FILTER (WHERE on_promo = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 1) AS promo_pct,
        COUNT(*) FILTER (WHERE is_fallback = TRUE) AS fallback_count,
        ROUND(COUNT(*) FILTER (WHERE is_fallback = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 1) AS fallback_pct,
        COUNT(*) FILTER (WHERE is_outlier = TRUE) AS outlier_count
    FROM silver.fct_daily_prices
    GROUP BY scrape_date, store_slug
) s ON s.scrape_date = r.scrape_date AND s.store_slug = r.store_slug
ORDER BY r.scrape_date DESC, r.record_count DESC;


-- 10.2 20-Source Scraper Availability Matrix (Current Live Health)
CREATE OR REPLACE VIEW gold.v_monitor_source_health_matrix AS
WITH source_stats AS (
    SELECT
        store_slug,
        MAX(scrape_date) AS latest_scrape_date,
        COUNT(DISTINCT scrape_date) AS active_days_recorded,
        ROUND(AVG(record_count), 0) AS avg_daily_volume_7d
    FROM staging.raw_scrapes
    WHERE scrape_date >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY store_slug
)
SELECT
    s.store_slug,
    s.latest_scrape_date,
    CURRENT_DATE - s.latest_scrape_date AS days_since_last_scrape,
    COALESCE(s.avg_daily_volume_7d, 0) AS avg_daily_volume_7d,
    s.active_days_recorded AS active_days_last_7d,
    CASE
        WHEN s.latest_scrape_date = CURRENT_DATE THEN 'ONLINE_FRESH'
        WHEN s.latest_scrape_date >= CURRENT_DATE - INTERVAL '1 day' THEN 'ONLINE_YESTERDAY'
        WHEN s.latest_scrape_date >= CURRENT_DATE - INTERVAL '3 days' THEN 'DELAYED_WARNING'
        ELSE 'OFFLINE_CRITICAL'
    END AS pipeline_health
FROM source_stats s
ORDER BY days_since_last_scrape ASC, avg_daily_volume_7d DESC;


-- 10.3 Daily Price Anomaly & Extreme Shift Alerts (> 20% DoD)
CREATE OR REPLACE VIEW gold.v_monitor_price_alerts AS
SELECT
    curr.scrape_date,
    curr.store_slug,
    curr.item_id,
    curr.name_clean,
    curr.coicop_division,
    prev.price_khr AS yesterday_price_khr,
    curr.price_khr AS today_price_khr,
    ROUND((curr.price_khr - prev.price_khr) / NULLIF(prev.price_khr, 0) * 100.0, 2) AS dod_price_change_pct,
    CASE
        WHEN curr.price_khr > prev.price_khr * 2.0 THEN 'CRITICAL_SPIKE (+100%)'
        WHEN curr.price_khr > prev.price_khr * 1.3 THEN 'HIGH_SURGE (+30%)'
        WHEN curr.price_khr < prev.price_khr * 0.5 THEN 'CRITICAL_DROP (-50%)'
        WHEN curr.price_khr < prev.price_khr * 0.7 THEN 'HIGH_DROP (-30%)'
        ELSE 'MODERATE_SHIFT'
    END AS alert_level
FROM silver.fct_daily_prices curr
JOIN silver.fct_daily_prices prev
  ON prev.item_id = curr.item_id
 AND prev.store_slug = curr.store_slug
 AND prev.scrape_date = (curr.scrape_date - INTERVAL '1 day')::DATE
WHERE curr.price_khr > 0
  AND prev.price_khr > 0
  AND ABS(curr.price_khr - prev.price_khr) / prev.price_khr >= 0.20
ORDER BY curr.scrape_date DESC, ABS((curr.price_khr - prev.price_khr) / prev.price_khr) DESC;


-- 10.4 MEF USD/KHR Exchange Rate Health & Freshness Monitor
CREATE OR REPLACE VIEW gold.v_monitor_fx_health AS
SELECT
    execution_date,
    rate AS usd_khr_exchange_rate,
    source,
    is_stale,
    fetched_at,
    ROUND((rate - LAG(rate) OVER (ORDER BY execution_date)) / NULLIF(LAG(rate) OVER (ORDER BY execution_date), 0) * 100.0, 3) AS dod_fx_change_pct,
    CASE
        WHEN is_stale = TRUE THEN 'STALE_WARNING'
        WHEN execution_date = CURRENT_DATE THEN 'FRESH_OFFICIAL'
        ELSE 'HISTORICAL'
    END AS fx_status
FROM staging.exchange_rates
ORDER BY execution_date DESC;
