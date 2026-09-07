-- ============================================================================
-- CAMBODIA CPI PIPELINE — OPERATIONS & MONITORING SERVING VIEWS
-- Sourced from gold.fct_daily_prices, gold.dim_items, gold.coicop_weights,
-- silver.clean_store_prices, and staging.exchange_rates.
-- ============================================================================


-- 5. View: Data Coverage and Pipeline Audit
CREATE OR REPLACE VIEW gold.v_coverage AS
SELECT
    d.scrape_date,
    d.store_slug,
    COUNT(*) AS total_observations,
    COUNT(DISTINCT d.item_id) AS unique_products,
    COUNT(*) FILTER (WHERE m.coicop_division IS NULL OR m.coicop_division = '99') AS unclassified_count,
    ROUND(COUNT(*) FILTER (WHERE m.coicop_division IS NOT NULL AND m.coicop_division <> '99')::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 2) AS classification_rate_pct,
    COUNT(*) FILTER (WHERE m.barcode IS NOT NULL) AS barcode_count,
    ROUND(COUNT(*) FILTER (WHERE m.barcode IS NOT NULL)::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 2) AS barcode_coverage_pct,
    COUNT(*) FILTER (WHERE d.is_outlier = TRUE) AS outlier_count
FROM gold.fct_daily_prices d
LEFT JOIN gold.dim_items m ON m.item_id = d.item_id
GROUP BY d.scrape_date, d.store_slug
ORDER BY d.scrape_date DESC, d.store_slug;


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
    FROM gold.fct_daily_prices
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
-- BUG-09 FIX: Use LAG() window function instead of a strict yesterday join,
-- so weekend and multi-day scraper gaps are handled correctly.
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


-- 10.5 4-Digit COICOP Class Breakdown Mart View (Metabase Granular Analytics)
CREATE OR REPLACE VIEW gold.v_coicop_class_breakdown AS
SELECT
    c.calculation_date,
    c.coicop_division,
    c.coicop_code,
    c.class_index,
    c.item_count,
    c.total_observations,
    c.imputed_item_count,
    ROUND((c.class_index - LAG(c.class_index) OVER (PARTITION BY c.coicop_code ORDER BY c.calculation_date)) / NULLIF(LAG(c.class_index) OVER (PARTITION BY c.coicop_code ORDER BY c.calculation_date), 0) * 100.0, 3) AS dod_class_change_pct
FROM gold.fct_coicop_class_daily c
ORDER BY c.calculation_date DESC, c.coicop_code ASC;


-- 10.6 National CPI Inflation Summary (Headline, Core, and ILO Imputation Metrics)
CREATE OR REPLACE VIEW gold.v_cpi_inflation_summary AS
SELECT
    f.calculation_date,
    f.headline_cpi,
    f.core_cpi,
    ROUND((f.headline_cpi - LAG(f.headline_cpi) OVER (ORDER BY f.calculation_date)) / NULLIF(LAG(f.headline_cpi) OVER (ORDER BY f.calculation_date), 0) * 100.0, 3) AS dod_headline_inflation_pct,
    ROUND((f.core_cpi - LAG(f.core_cpi) OVER (ORDER BY f.calculation_date)) / NULLIF(LAG(f.core_cpi) OVER (ORDER BY f.calculation_date), 0) * 100.0, 3) AS dod_core_inflation_pct,
    f.total_items AS active_basket_items,
    f.total_observations
FROM (
    SELECT
        calculation_date,
        MAX(headline_cpi) AS headline_cpi,
        MAX(core_cpi) AS core_cpi,
        SUM(item_count) AS total_items,
        SUM(observation_count) AS total_observations
    FROM gold.fct_cpi_daily
    GROUP BY calculation_date
) f
ORDER BY f.calculation_date DESC;


-- 10.7 Monthly National CPI Inflation Summary (Headline & Core MoM / YoY)
CREATE OR REPLACE VIEW gold.v_cpi_monthly_summary AS
WITH monthly_base AS (
    SELECT
        DATE_TRUNC('month', calculation_date)::DATE AS cpi_month,
        ROUND(AVG(headline_cpi), 4) AS monthly_headline_cpi,
        ROUND(AVG(core_cpi), 4) AS monthly_core_cpi,
        COUNT(DISTINCT calculation_date) AS active_days_in_month,
        SUM(observation_count) AS total_observations,
        SUM(item_count) AS total_items
    FROM (
        SELECT
            calculation_date,
            MAX(headline_cpi) AS headline_cpi,
            MAX(core_cpi) AS core_cpi,
            SUM(observation_count) AS observation_count,
            SUM(item_count) AS item_count
        FROM gold.fct_cpi_daily
        GROUP BY calculation_date
    ) d
    GROUP BY DATE_TRUNC('month', calculation_date)::DATE
)
SELECT
    curr.cpi_month,
    curr.monthly_headline_cpi,
    curr.monthly_core_cpi,
    curr.active_days_in_month,
    curr.total_observations,
    ROUND(((curr.monthly_headline_cpi - prev_m.monthly_headline_cpi) / NULLIF(prev_m.monthly_headline_cpi, 0) * 100.0)::NUMERIC, 2) AS headline_mom_inflation_pct,
    ROUND(((curr.monthly_core_cpi - prev_m.monthly_core_cpi) / NULLIF(prev_m.monthly_core_cpi, 0) * 100.0)::NUMERIC, 2) AS core_mom_inflation_pct,
    ROUND(((curr.monthly_headline_cpi - prev_y.monthly_headline_cpi) / NULLIF(prev_y.monthly_headline_cpi, 0) * 100.0)::NUMERIC, 2) AS headline_yoy_inflation_pct,
    ROUND(((curr.monthly_core_cpi - prev_y.monthly_core_cpi) / NULLIF(prev_y.monthly_core_cpi, 0) * 100.0)::NUMERIC, 2) AS core_yoy_inflation_pct
FROM monthly_base curr
LEFT JOIN monthly_base prev_m ON prev_m.cpi_month = (curr.cpi_month - INTERVAL '1 month')::DATE
LEFT JOIN monthly_base prev_y ON prev_y.cpi_month = (curr.cpi_month - INTERVAL '1 year')::DATE
ORDER BY curr.cpi_month DESC;


-- 10.8 Monthly 12-Division COICOP Breakdown Matrix
CREATE OR REPLACE VIEW gold.v_cpi_monthly_divisions AS
WITH div_monthly AS (
    SELECT
        DATE_TRUNC('month', calculation_date)::DATE AS cpi_month,
        coicop_division,
        MAX(division_name) AS division_name,
        MAX(weight) AS weight,
        ROUND(AVG(division_index), 4) AS monthly_division_index,
        SUM(observation_count) AS total_observations,
        COUNT(DISTINCT calculation_date) AS active_days_in_month
    FROM gold.fct_cpi_daily
    GROUP BY DATE_TRUNC('month', calculation_date)::DATE, coicop_division
)
SELECT
    curr.cpi_month,
    curr.coicop_division,
    curr.division_name,
    curr.weight,
    curr.monthly_division_index,
    ROUND(((curr.monthly_division_index - prev_m.monthly_division_index) / NULLIF(prev_m.monthly_division_index, 0) * 100.0)::NUMERIC, 2) AS division_mom_change_pct,
    ROUND(((curr.monthly_division_index - prev_y.monthly_division_index) / NULLIF(prev_y.monthly_division_index, 0) * 100.0)::NUMERIC, 2) AS division_yoy_change_pct,
    curr.total_observations,
    curr.active_days_in_month
FROM div_monthly curr
LEFT JOIN div_monthly prev_m ON prev_m.coicop_division = curr.coicop_division AND prev_m.cpi_month = (curr.cpi_month - INTERVAL '1 month')::DATE
LEFT JOIN div_monthly prev_y ON prev_y.coicop_division = curr.coicop_division AND prev_y.cpi_month = (curr.cpi_month - INTERVAL '1 year')::DATE
ORDER BY curr.cpi_month DESC, curr.coicop_division ASC;


-- 10.9 Out-of-Sample Nowcasting Evaluation & Tracking vs. Official NIS Benchmarks
CREATE OR REPLACE VIEW gold.v_nowcast_evaluation AS
SELECT 
    n.nowcast_date,
    n.target_month,
    n.days_observed,
    n.days_remaining,
    n.projected_mom_pct AS nowcasted_mom_pct,
    o.mom_inflation_pct AS actual_nis_mom_pct,
    ROUND(n.projected_mom_pct - o.mom_inflation_pct, 4) AS mom_forecast_error,
    n.nowcast_nis_headline_cpi AS nowcasted_nis_cpi,
    o.headline_cpi AS actual_nis_cpi,
    ROUND(n.nowcast_nis_headline_cpi - o.headline_cpi, 4) AS cpi_forecast_error,
    n.ci_lower_95,
    n.ci_upper_95,
    CASE 
        WHEN o.headline_cpi BETWEEN n.ci_lower_95 AND n.ci_upper_95 THEN TRUE 
        ELSE FALSE 
    END AS is_within_95_ci,
    n.model_name
FROM gold.fct_cpi_nowcast n
LEFT JOIN gold.dim_nis_official_cpi o ON n.target_month = o.cpi_month
ORDER BY n.nowcast_date DESC;


