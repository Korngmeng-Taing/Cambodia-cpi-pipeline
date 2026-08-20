-- ============================================================================
-- CAMBODIA CPI PIPELINE — ANALYTICAL VIEWS (SERVING & METABASE DASHBOARDS)
-- Sourced entirely from dbt tables (gold.cpi_headline_daily, silver.fct_daily_prices,
-- gold.fct_daily_price_stats, silver.item_master, gold.coicop_weights, staging.exchange_rates).
-- ============================================================================

-- 1. View: Latest Headline CPI and Summary
CREATE OR REPLACE VIEW gold.v_cpi_latest AS
WITH latest_date AS (
    SELECT MAX(scrape_date) AS max_date FROM gold.cpi_headline_daily
),
current_cpi AS (
    SELECT h.*
    FROM gold.cpi_headline_daily h
    JOIN latest_date l ON h.scrape_date = l.max_date
    WHERE h.formula = 'Laspeyres'
),
prev_day AS (
    SELECT index_value AS prev_day_index
    FROM gold.cpi_headline_daily
    WHERE scrape_date = (SELECT max_date - INTERVAL '1 day' FROM latest_date)
      AND formula = 'Laspeyres'
),
prev_month AS (
    SELECT index_value AS prev_month_index
    FROM gold.cpi_headline_daily
    WHERE scrape_date = (SELECT max_date - INTERVAL '1 month' FROM latest_date)
      AND formula = 'Laspeyres'
)
SELECT
    c.scrape_date,
    c.base_period,
    c.index_value AS headline_cpi,
    c.divisions_present,
    c.total_weight_present,
    ROUND((c.index_value - pd.prev_day_index) / NULLIF(pd.prev_day_index, 0) * 100.0, 2) AS dod_change_pct,
    ROUND((c.index_value - pm.prev_month_index) / NULLIF(pm.prev_month_index, 0) * 100.0, 2) AS mom_change_pct
FROM current_cpi c
LEFT JOIN prev_day pd ON TRUE
LEFT JOIN prev_month pm ON TRUE;


-- 2. View: Inflation Time Series (DoD and MoM)
CREATE OR REPLACE VIEW gold.v_inflation AS
SELECT
    curr.scrape_date,
    curr.formula,
    curr.index_value AS cpi,
    ROUND((curr.index_value - prev_d.index_value) / NULLIF(prev_d.index_value, 0) * 100.0, 3) AS dod_inflation_pct,
    ROUND((curr.index_value - prev_m.index_value) / NULLIF(prev_m.index_value, 0) * 100.0, 3) AS mom_inflation_pct
FROM gold.cpi_headline_daily curr
LEFT JOIN gold.cpi_headline_daily prev_d
    ON prev_d.scrape_date = (curr.scrape_date - INTERVAL '1 day')::DATE
   AND prev_d.formula = curr.formula
LEFT JOIN gold.cpi_headline_daily prev_m
    ON prev_m.scrape_date = (curr.scrape_date - INTERVAL '1 month')::DATE
   AND prev_m.formula = curr.formula
ORDER BY curr.scrape_date DESC;


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


-- 6. View: Elementary Jevons Index & Relatives (Silver Layer)
DROP VIEW IF EXISTS silver.fct_jevons_daily CASCADE;
CREATE VIEW silver.fct_jevons_daily AS
WITH clean_obs AS (
SELECT
        scrape_date,
        item_id,
        coicop_division,
        price_khr,
        unit_price_khr,
        size_unit,
        store_slug
    FROM silver.fct_daily_prices
    WHERE cpi_eligible = TRUE
      AND is_outlier = FALSE
      AND is_fallback = FALSE
      AND price_khr > 0
),
daily_jevons AS (
    SELECT
        scrape_date,
        item_id,
        coicop_division,
-- Unit-price-aware elementary price (mirrors gold_procedures.sql): use per-kg/L
        -- unit prices only when every quote carries a comparable base dimension, else shelf price.
        ROUND(
            CASE
                WHEN COUNT(*) FILTER (WHERE unit_price_khr > 0) = COUNT(*)
                 AND COUNT(DISTINCT CASE WHEN size_unit IN ('kg','g') THEN 1 WHEN size_unit IN ('l','ml') THEN 2 END) = 1
                THEN EXP(AVG(LN(unit_price_khr)) FILTER (WHERE unit_price_khr > 0))
                ELSE EXP(AVG(LN(price_khr)) FILTER (WHERE price_khr > 0))
            END, 2) AS p_khr_jevons,
        ROUND(EXP(AVG(LN(NULLIF(unit_price_khr, 0)))), 2) AS unit_price_khr_jevons,
        COUNT(*) AS n_quotes,
        COUNT(DISTINCT store_slug) AS n_stores
    FROM clean_obs
    GROUP BY scrape_date, item_id, coicop_division
)
SELECT
    curr.scrape_date,
    curr.item_id,
    curr.coicop_division,
    curr.p_khr_jevons,
    b.base_price_khr,
    ROUND((curr.p_khr_jevons / NULLIF(b.base_price_khr, 0)) * 100.0, 4) AS jevons_index_base,
    curr.unit_price_khr_jevons,
    curr.n_quotes,
    curr.n_stores,
    ROUND((curr.p_khr_jevons - prev.p_khr_jevons) / NULLIF(prev.p_khr_jevons, 0) * 100.0, 3) AS dod_price_change_pct,
    ROUND(curr.p_khr_jevons / NULLIF(prev.p_khr_jevons, 0), 4) AS jevons_rel_dod
FROM daily_jevons curr
LEFT JOIN gold.base_prices b
    ON b.product_key = curr.item_id
   AND b.base_period = '2026-08'
LEFT JOIN daily_jevons prev
    ON curr.item_id = prev.item_id
   AND prev.scrape_date = (curr.scrape_date - INTERVAL '1 day')::DATE;


-- 7. View: Higher-Level Laspeyres Category Aggregation (Silver Layer)
DROP VIEW IF EXISTS silver.fct_laspeyres_daily CASCADE;
CREATE VIEW silver.fct_laspeyres_daily AS
WITH category_indices AS (
    SELECT
        j.scrape_date,
        j.coicop_division,
        w.division_name,
        w.weight_pct,
        ROUND(EXP(AVG(LN(NULLIF(j.p_khr_jevons / NULLIF(j.base_price_khr, 0), 0)))) * 100.0, 4) AS category_index_value,
        COUNT(*) AS n_items,
        COUNT(DISTINCT j.item_id) AS unique_products
    FROM silver.fct_jevons_daily j
    INNER JOIN gold.coicop_weights w
        ON w.coicop_division = j.coicop_division
    WHERE j.p_khr_jevons > 0
      AND j.base_price_khr > 0
    GROUP BY
        j.scrape_date,
        j.coicop_division,
        w.division_name,
        w.weight_pct
),
category_with_prev AS (
    SELECT
        curr.scrape_date,
        curr.coicop_division,
        curr.division_name,
        curr.weight_pct,
        curr.category_index_value,
        curr.n_items,
        curr.unique_products,
        ROUND((curr.category_index_value - prev.category_index_value) / NULLIF(prev.category_index_value, 0) * 100.0, 3) AS dod_category_change_pct
    FROM category_indices curr
    LEFT JOIN category_indices prev
        ON curr.coicop_division = prev.coicop_division
       AND prev.scrape_date = (curr.scrape_date - INTERVAL '1 day')::DATE
)
SELECT
    scrape_date,
    coicop_division,
    division_name,
    weight_pct,
    category_index_value,
    n_items,
    unique_products,
    dod_category_change_pct,
    'Laspeyres' AS formula_type
FROM category_with_prev;


-- 8. View: Headline Laspeyres CPI Aggregation (Silver Layer)
DROP VIEW IF EXISTS silver.fct_laspeyres_headline_daily CASCADE;
CREATE VIEW silver.fct_laspeyres_headline_daily AS
WITH daily_headline AS (
    SELECT
        scrape_date,
        '2026-08' AS base_period,
        ROUND(SUM(category_index_value * (weight_pct / 100.0)) / NULLIF(SUM(weight_pct / 100.0), 0), 4) AS headline_cpi,
        COUNT(DISTINCT coicop_division) AS divisions_present,
        SUM(weight_pct) AS total_weight_present,
        'Laspeyres' AS formula
    FROM silver.fct_laspeyres_daily
    GROUP BY scrape_date
)
SELECT
    curr.scrape_date,
    curr.base_period,
    curr.headline_cpi,
    curr.divisions_present,
    curr.total_weight_present,
    curr.formula,
    ROUND((curr.headline_cpi - prev.headline_cpi) / NULLIF(prev.headline_cpi, 0) * 100.0, 3) AS dod_inflation_pct
FROM daily_headline curr
LEFT JOIN daily_headline prev
    ON prev.scrape_date = (curr.scrape_date - INTERVAL '1 day')::DATE;





-- ============================================================================
-- 12 DEDICATED GOLD COICOP DIVISION TABLES / VIEWS
-- ============================================================================

-- Gold Division 01: Food and non-alcoholic beverages
DROP VIEW IF EXISTS gold.cpi_div01_food CASCADE;
CREATE VIEW gold.cpi_div01_food AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '01' AS coicop_division,
    'Food and non-alcoholic beverages' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '01';


-- Gold Division 02: Alcoholic beverages, tobacco and narcotics
DROP VIEW IF EXISTS gold.cpi_div02_alcohol_tobacco CASCADE;
CREATE VIEW gold.cpi_div02_alcohol_tobacco AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '02' AS coicop_division,
    'Alcoholic beverages, tobacco and narcotics' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '02';


-- Gold Division 03: Clothing and footwear
DROP VIEW IF EXISTS gold.cpi_div03_clothing_footwear CASCADE;
CREATE VIEW gold.cpi_div03_clothing_footwear AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '03' AS coicop_division,
    'Clothing and footwear' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '03';


-- Gold Division 04: Housing, water, electricity, gas and other fuels
DROP VIEW IF EXISTS gold.cpi_div04_housing_utilities CASCADE;
CREATE VIEW gold.cpi_div04_housing_utilities AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '04' AS coicop_division,
    'Housing, water, electricity, gas and other fuels' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '04';


-- Gold Division 05: Furnishings, household equipment and routine household maintenance
DROP VIEW IF EXISTS gold.cpi_div05_furnishings CASCADE;
CREATE VIEW gold.cpi_div05_furnishings AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '05' AS coicop_division,
    'Furnishings, household equipment and routine household maintenance' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '05';


-- Gold Division 06: Health
DROP VIEW IF EXISTS gold.cpi_div06_health CASCADE;
CREATE VIEW gold.cpi_div06_health AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '06' AS coicop_division,
    'Health' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '06';


-- Gold Division 07: Transport
DROP VIEW IF EXISTS gold.cpi_div07_transport CASCADE;
CREATE VIEW gold.cpi_div07_transport AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '07' AS coicop_division,
    'Transport' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '07';


-- Gold Division 08: Communication
DROP VIEW IF EXISTS gold.cpi_div08_communication CASCADE;
CREATE VIEW gold.cpi_div08_communication AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '08' AS coicop_division,
    'Communication' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '08';


-- Gold Division 09: Recreation and culture
DROP VIEW IF EXISTS gold.cpi_div09_recreation CASCADE;
CREATE VIEW gold.cpi_div09_recreation AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '09' AS coicop_division,
    'Recreation and culture' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '09';


-- Gold Division 10: Education
DROP VIEW IF EXISTS gold.cpi_div10_education CASCADE;
CREATE VIEW gold.cpi_div10_education AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '10' AS coicop_division,
    'Education' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '10';


-- Gold Division 11: Restaurants and hotels
DROP VIEW IF EXISTS gold.cpi_div11_restaurants_hotels CASCADE;
CREATE VIEW gold.cpi_div11_restaurants_hotels AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '11' AS coicop_division,
    'Restaurants and hotels' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '11';


-- Gold Division 12: Miscellaneous goods and services
DROP VIEW IF EXISTS gold.cpi_div12_misc CASCADE;
CREATE VIEW gold.cpi_div12_misc AS
SELECT
    j.scrape_date,
    j.item_id,
    m.canonical_name,
    '12' AS coicop_division,
    'Miscellaneous goods and services' AS division_name,
    j.p_khr_jevons AS current_price_khr,
    j.base_price_khr,
    j.jevons_index_base AS item_index_base,
    j.unit_price_khr_jevons AS unit_price_khr,
    j.n_quotes,
    j.n_stores,
    j.dod_price_change_pct,
    j.jevons_rel_dod
FROM silver.fct_jevons_daily j
LEFT JOIN silver.dim_items m
    ON m.item_id = j.item_id
WHERE j.coicop_division = '12';


-- ============================================================================
-- 9. View: Observed-Only Inflation (excludes LOCF-imputed rows from change calcs)
--    DoD/MoM inflation computed on actually-observed quotes only, so forward-carried
--    prices (is_imputed=TRUE) cannot smooth or zero out real price moves.
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

