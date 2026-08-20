-- ============================================================================
-- CAMBODIA CPI PIPELINE — GOLD STORED PROCEDURES (SQL-FIRST INDEX CALCULATION)
-- ============================================================================

-- 1. Procedure: Bootstrap Base Prices from Base Period observations
CREATE OR REPLACE PROCEDURE gold.sp_bootstrap_base_prices(p_base_period VARCHAR(7))
LANGUAGE plpgsql AS $$
DECLARE
    v_base_start DATE := TO_DATE(p_base_period || '-01', 'YYYY-MM-DD');
    v_base_end DATE := (v_base_start + INTERVAL '1 month')::DATE;
    v_count INT;
BEGIN
    -- Delete existing base prices for this period
    DELETE FROM gold.base_prices WHERE base_period = p_base_period;

    -- Compute geometric mean base price for canonical items with n_obs >= 1
    -- Division is resolved at the canonical item level (dim_items.coicop_division)
    INSERT INTO gold.base_prices (product_key, base_period, base_price_khr, n_obs, std_dev, coicop_division, created_at)
    SELECT 
        d.item_id AS product_key,
        p_base_period,
        ROUND(
            CASE
                WHEN COUNT(*) FILTER (WHERE d.unit_price_khr > 0) = COUNT(*)
                 AND COUNT(DISTINCT CASE WHEN d.size_unit IN ('kg','g') THEN 1 WHEN d.size_unit IN ('l','ml') THEN 2 END) = 1
                THEN EXP(AVG(LN(d.unit_price_khr)) FILTER (WHERE d.unit_price_khr > 0))
                ELSE EXP(AVG(LN(d.price_khr)) FILTER (WHERE d.price_khr > 0))
            END,
            2
        ) AS base_price_khr,
        COUNT(*) AS n_obs,
        ROUND(STDDEV_SAMP(d.price_khr), 2) AS std_dev,
        COALESCE(ci.coicop_division, 'UNCLASSIFIED') AS coicop_division,
        NOW()
    FROM silver.fct_daily_prices d
    LEFT JOIN silver.dim_items ci ON ci.item_id = d.item_id
    WHERE d.scrape_date >= v_base_start 
      AND d.scrape_date < v_base_end
      AND d.cpi_eligible = TRUE 
      AND d.is_fallback = FALSE 
      AND d.is_outlier = FALSE
      AND d.price_khr > 0
    GROUP BY d.item_id, ci.coicop_division
    HAVING COUNT(*) >= 1;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'Bootstrapped % base prices for period % (observations between % and %)', 
        v_count, p_base_period, v_base_start, v_base_end;
END;
$$;


-- 1b. Procedure: Ensure base prices exist for the base period (idempotent).
--     Freeze semantics: base prices are bootstrapped ONCE per base period and never
--     silently recomputed, so historical indices do not shift (re-anchoring trap).
--     Use gold.sp_bootstrap_base_prices directly to force a refresh (manual re-baseline).
CREATE OR REPLACE PROCEDURE gold.sp_ensure_base_prices(p_base_period VARCHAR(7))
LANGUAGE plpgsql AS $$
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(*) INTO v_count FROM gold.base_prices WHERE base_period = p_base_period;
    IF v_count = 0 THEN
        RAISE NOTICE 'No frozen base prices for % — bootstrapping.', p_base_period;
        CALL gold.sp_bootstrap_base_prices(p_base_period);
    ELSE
        RAISE NOTICE 'Base prices already frozen for % (% rows) — skipping bootstrap.', p_base_period, v_count;
    END IF;
END;
$$;


-- 2. Procedure: Calculate Daily CPI Index (Elementary Jevons, Gap-Fill, Laspeyres, Anomalies)
CREATE OR REPLACE PROCEDURE gold.sp_calculate_daily_cpi(p_date DATE)
LANGUAGE plpgsql AS $$
DECLARE
    v_base_period VARCHAR(7) := '2026-08';
    v_total_weight NUMERIC(6,3);
    v_div_count INT;
BEGIN
    -- Step 1: Elementary Aggregation — Jevons Geometric Mean per item_id
    INSERT INTO gold.fct_daily_price_stats (
        scrape_date, item_id, coicop_division, p_khr_jevons, p_khr_unit, n_quotes, n_stores, is_imputed, gap_days
    )
    SELECT 
        p_date,
        d.item_id,
        COALESCE(ci.coicop_division, 'UNCLASSIFIED') AS coicop_division,
        -- Unit-price-aware elementary price: when every quote for this item/day
        -- carries a comparable per-kg or per-L unit price (same base dimension), the
        -- Jevons mean is taken over unit prices so pack-size changes cannot masquerade
        -- as inflation (Layer 6). Otherwise fall back to the shelf price.
        ROUND(
            CASE
                WHEN COUNT(*) FILTER (WHERE d.unit_price_khr > 0) = COUNT(*)
                 AND COUNT(DISTINCT CASE WHEN d.size_unit IN ('kg','g') THEN 1 WHEN d.size_unit IN ('l','ml') THEN 2 END) = 1
                THEN EXP(AVG(LN(d.unit_price_khr)) FILTER (WHERE d.unit_price_khr > 0))
                ELSE EXP(AVG(LN(d.price_khr)) FILTER (WHERE d.price_khr > 0))
            END,
            2
        ) AS p_khr_jevons,
        ROUND(EXP(AVG(LN(NULLIF(d.unit_price_khr, 0)))), 2) AS p_khr_unit,
        COUNT(*) AS n_quotes,
        COUNT(DISTINCT d.store_slug) AS n_stores,
        FALSE AS is_imputed,
        0 AS gap_days
    FROM silver.fct_daily_prices d
    LEFT JOIN silver.dim_items ci ON ci.item_id = d.item_id
    WHERE d.scrape_date = p_date 
      AND d.cpi_eligible = TRUE 
      AND d.is_fallback = FALSE 
      AND d.is_outlier = FALSE
      AND d.price_khr > 0
    GROUP BY d.item_id, ci.coicop_division
    ON CONFLICT (scrape_date, item_id) DO UPDATE 
    SET coicop_division = EXCLUDED.coicop_division,
        p_khr_jevons = EXCLUDED.p_khr_jevons,
        p_khr_unit = EXCLUDED.p_khr_unit,
        n_quotes = EXCLUDED.n_quotes,
        n_stores = EXCLUDED.n_stores,
        is_imputed = FALSE,
        gap_days = 0;

    -- Step 2: Gap-Filling — Forward carry unobserved items up to <= 7 consecutive days
    INSERT INTO gold.fct_daily_price_stats (
        scrape_date, item_id, coicop_division, p_khr_jevons, p_khr_unit, n_quotes, n_stores, is_imputed, gap_days
    )
    SELECT 
        p_date,
        prev.item_id,
        prev.coicop_division,
        prev.p_khr_jevons,
        prev.p_khr_unit,
        prev.n_quotes,
        prev.n_stores,
        TRUE AS is_imputed,
        prev.gap_days + 1 AS gap_days
    FROM gold.fct_daily_price_stats prev
    WHERE prev.scrape_date = (p_date - INTERVAL '1 day')::DATE
      AND prev.gap_days < 7
      AND prev.item_id NOT IN (
          SELECT item_id FROM gold.fct_daily_price_stats WHERE scrape_date = p_date
      )
    ON CONFLICT (scrape_date, item_id) DO NOTHING;

    -- Step 3: Category (Division) Aggregation (Jevons elementary relative over base prices)
    DELETE FROM gold.cpi_category_daily WHERE scrape_date = p_date;
    INSERT INTO gold.cpi_category_daily (scrape_date, coicop_division, index_value, base_period, n_items, weight_pct)
    SELECT 
        p_date,
        d.coicop_division,
        ROUND(EXP(AVG(LN(d.p_khr_jevons / b.base_price_khr))) * 100.0, 4) AS index_value,
        v_base_period,
        COUNT(d.item_id) AS n_items,
        w.weight_pct
    FROM gold.fct_daily_price_stats d
    JOIN gold.base_prices b ON d.item_id = b.product_key AND b.base_period = v_base_period
    JOIN gold.coicop_weights w ON d.coicop_division = w.coicop_division
    WHERE d.scrape_date = p_date
    GROUP BY d.coicop_division, w.weight_pct;

    -- Step 3b: Populate Unified 12 COICOP Division Mart (gold.mart_cpi_division_daily)
    DELETE FROM gold.mart_cpi_division_daily WHERE scrape_date = p_date;
    INSERT INTO gold.mart_cpi_division_daily (
        scrape_date, coicop_division, division_name, weight_pct,
        division_index_khr, division_index_usd, dod_change_pct, mom_change_pct,
        active_items_count, stores_count, promo_share_pct, calculated_at
    )
    WITH div_stats AS (
        SELECT 
            c.coicop_division,
            w.division_name,
            w.weight_pct,
            c.index_value AS idx_khr,
            ROUND(c.index_value * COALESCE(er.rate, 4044.0) / 4044.0, 4) AS idx_usd,
            c.n_items,
            COUNT(DISTINCT f.store_slug) AS n_stores,
            ROUND(COUNT(*) FILTER (WHERE f.on_promo = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 2) AS promo_share
        FROM gold.cpi_category_daily c
        JOIN gold.coicop_weights w ON w.coicop_division = c.coicop_division
        LEFT JOIN staging.exchange_rates er ON er.execution_date = p_date
        LEFT JOIN silver.fct_daily_prices f ON f.scrape_date = p_date AND f.coicop_division = c.coicop_division
        WHERE c.scrape_date = p_date
        GROUP BY c.coicop_division, w.division_name, w.weight_pct, c.index_value, er.rate, c.n_items
    ),
    prev_div AS (
        SELECT coicop_division, division_index_khr
        FROM gold.mart_cpi_division_daily
        WHERE scrape_date = (p_date - INTERVAL '1 day')::DATE
    ),
    prev_div_m AS (
        SELECT coicop_division, division_index_khr
        FROM gold.mart_cpi_division_daily
        WHERE scrape_date = (p_date - INTERVAL '1 month')::DATE
    )
    SELECT 
        p_date,
        s.coicop_division,
        s.division_name,
        s.weight_pct,
        s.idx_khr,
        s.idx_usd,
        ROUND((s.idx_khr - pd.division_index_khr) / NULLIF(pd.division_index_khr, 0) * 100.0, 3) AS dod_change_pct,
        ROUND((s.idx_khr - pm.division_index_khr) / NULLIF(pm.division_index_khr, 0) * 100.0, 3) AS mom_change_pct,
        s.n_items,
        s.n_stores,
        COALESCE(s.promo_share, 0.00),
        NOW()
    FROM div_stats s
    LEFT JOIN prev_div pd ON pd.coicop_division = s.coicop_division
    LEFT JOIN prev_div_m pm ON pm.coicop_division = s.coicop_division;

    -- Step 4: Overall Headline CPI & Core CPI
    SELECT COALESCE(SUM(weight_pct), 0.0), COUNT(*) 
    INTO v_total_weight, v_div_count 
    FROM gold.cpi_category_daily 
    WHERE scrape_date = p_date;

    IF v_total_weight > 0 THEN
        DELETE FROM gold.cpi_headline_daily WHERE scrape_date = p_date AND formula = 'Laspeyres';
        INSERT INTO gold.cpi_headline_daily (scrape_date, base_period, index_value, formula, divisions_present, total_weight_present)
        SELECT 
            p_date,
            v_base_period,
            ROUND(SUM(index_value * (weight_pct / NULLIF(v_total_weight, 0))), 4),
            'Laspeyres',
            v_div_count,
            v_total_weight
        FROM gold.cpi_category_daily
        WHERE scrape_date = p_date;

        -- Step 4b: Populate Unified National Headline & Core CPI Mart (gold.mart_cpi_daily)
        DELETE FROM gold.mart_cpi_daily WHERE scrape_date = p_date;
        INSERT INTO gold.mart_cpi_daily (
            scrape_date, base_period, cpi_headline_khr, cpi_headline_usd,
            cpi_geks_multilateral, cpi_core_khr, inflation_dod_pct, inflation_mom_pct,
            divisions_present, total_weight_covered, active_quotes_count, imputed_quote_pct, calculated_at
        )
        WITH current_headline AS (
            SELECT 
                ROUND(SUM(index_value * (weight_pct / NULLIF(v_total_weight, 0))), 4) AS headline_khr,
                -- Core CPI excludes Division 01 (Food) & 07 (Transport/Fuel)
                ROUND(
                    SUM(CASE WHEN coicop_division NOT IN ('01', '07') THEN index_value * weight_pct END) /
                    NULLIF(SUM(CASE WHEN coicop_division NOT IN ('01', '07') THEN weight_pct END), 0),
                    4
                ) AS core_khr
            FROM gold.cpi_category_daily
            WHERE scrape_date = p_date
        ),
        prev_headline AS (
            SELECT cpi_headline_khr 
            FROM gold.mart_cpi_daily 
            WHERE scrape_date = (p_date - INTERVAL '1 day')::DATE
        ),
        prev_month_headline AS (
            SELECT cpi_headline_khr 
            FROM gold.mart_cpi_daily 
            WHERE scrape_date = (p_date - INTERVAL '1 month')::DATE
        ),
        geks_val AS (
            SELECT index_value 
            FROM gold.cpi_geks_multilateral 
            WHERE scrape_date = p_date 
            ORDER BY calculated_at DESC 
            LIMIT 1
        ),
        quote_stats AS (
            SELECT 
                COUNT(*) AS total_q,
                ROUND(COUNT(*) FILTER (WHERE is_imputed = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100.0, 2) AS imp_pct
            FROM gold.fct_daily_price_stats
            WHERE scrape_date = p_date
        )
        SELECT 
            p_date,
            v_base_period,
            ch.headline_khr,
            ROUND(ch.headline_khr * COALESCE(er.rate, 4044.0) / 4044.0, 4) AS cpi_headline_usd,
            gv.index_value AS cpi_geks_multilateral,
            COALESCE(ch.core_khr, ch.headline_khr) AS cpi_core_khr,
            ROUND((ch.headline_khr - ph.cpi_headline_khr) / NULLIF(ph.cpi_headline_khr, 0) * 100.0, 3) AS inflation_dod_pct,
            ROUND((ch.headline_khr - pmh.cpi_headline_khr) / NULLIF(pmh.cpi_headline_khr, 0) * 100.0, 3) AS inflation_mom_pct,
            v_div_count,
            v_total_weight,
            COALESCE(qs.total_q, 0),
            COALESCE(qs.imp_pct, 0.00),
            NOW()
        FROM current_headline ch
        CROSS JOIN quote_stats qs
        LEFT JOIN staging.exchange_rates er ON er.execution_date = p_date
        LEFT JOIN prev_headline ph ON TRUE
        LEFT JOIN prev_month_headline pmh ON TRUE
        LEFT JOIN geks_val gv ON TRUE;
    END IF;

    -- Step 5: Price Anomaly Detection & Mart Population
    DELETE FROM gold.price_anomalies WHERE scrape_date = p_date;
    DELETE FROM gold.mart_price_anomalies WHERE scrape_date = p_date;

    INSERT INTO gold.price_anomalies (scrape_date, product_key, store_slug, price_khr, expected_price_khr, pct_change, anomaly_type)
    SELECT 
        curr.scrape_date,
        curr.item_id AS product_key,
        curr.store_slug,
        curr.price_khr,
        prev.price_khr AS expected_price_khr,
        ROUND(((curr.price_khr - prev.price_khr) / prev.price_khr * 100.0), 2) AS pct_change,
        CASE WHEN curr.price_khr > prev.price_khr THEN 'SPIKE_UP' ELSE 'CRASH_DOWN' END AS anomaly_type
    FROM silver.fct_daily_prices curr
    JOIN silver.fct_daily_prices prev 
      ON curr.item_id = prev.item_id 
     AND curr.store_slug = prev.store_slug 
     AND prev.scrape_date = (p_date - INTERVAL '1 day')::DATE
    WHERE curr.scrape_date = p_date
      AND prev.price_khr > 0
      AND ABS((curr.price_khr - prev.price_khr) / prev.price_khr) > 0.15;

    INSERT INTO gold.mart_price_anomalies (
        scrape_date, item_id, product_key, store_slug, canonical_name,
        coicop_division, price_khr, expected_price_khr, pct_change,
        anomaly_type, root_cause_flag, is_reviewed, created_at
    )
    SELECT 
        curr.scrape_date,
        curr.item_id,
        curr.item_id AS product_key,
        curr.store_slug,
        curr.name_clean AS canonical_name,
        curr.coicop_division,
        curr.price_khr,
        prev.price_khr AS expected_price_khr,
        ROUND(((curr.price_khr - prev.price_khr) / prev.price_khr * 100.0), 2) AS pct_change,
        CASE WHEN curr.price_khr > prev.price_khr THEN 'SPIKE_UP' ELSE 'CRASH_DOWN' END AS anomaly_type,
        CASE 
            WHEN curr.on_promo <> prev.on_promo THEN 'PROMO_SHIFT'
            WHEN ABS((curr.price_khr - prev.price_khr) / prev.price_khr) > 0.50 THEN 'SUSPECTED_PARSING_ERROR'
            ELSE 'GENUINE_PRICE_VOLATILITY'
        END AS root_cause_flag,
        FALSE AS is_reviewed,
        NOW()
    FROM silver.fct_daily_prices curr
    JOIN silver.fct_daily_prices prev 
      ON curr.item_id = prev.item_id 
     AND curr.store_slug = prev.store_slug 
     AND prev.scrape_date = (p_date - INTERVAL '1 day')::DATE
    WHERE curr.scrape_date = p_date
      AND prev.price_khr > 0
      AND ABS((curr.price_khr - prev.price_khr) / prev.price_khr) > 0.15;
END;
$$;
