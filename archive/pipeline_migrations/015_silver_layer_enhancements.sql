-- 015_silver_layer_enhancements.sql
-- Implements Silver Layer Enhancements:
-- 1. Cross-Store Retail Price Dispersion View (silver.v_cross_store_dispersion)
-- 2. Promotional Volatility & Discount Analytics View (silver.v_promo_analytics)
-- 3. Automated Monthly Partition Maintenance Procedure (silver.sp_create_monthly_partitions)

-- 1. Cross-Store Retail Price Dispersion View
CREATE OR REPLACE VIEW silver.v_cross_store_dispersion AS
SELECT 
    f.scrape_date,
    f.item_id,
    ci.canonical_name,
    di.brand,
    di.coicop_division,
    di.coicop_code,
    count(DISTINCT f.store_slug) AS retailer_count,
    string_agg(DISTINCT f.store_slug, ', ' ORDER BY f.store_slug) AS available_stores,
    min(f.price_khr) AS min_price_khr,
    max(f.price_khr) AS max_price_khr,
    round(avg(f.price_khr), 2) AS avg_price_khr,
    round(((max(f.price_khr) - min(f.price_khr)) / nullif(min(f.price_khr), 0)) * 100.0, 1) AS price_spread_pct,
    round(min(f.price_khr) / 4044.0, 2) AS min_price_usd,
    round(max(f.price_khr) / 4044.0, 2) AS max_price_usd,
    (ARRAY_AGG(f.store_slug ORDER BY f.price_khr ASC))[1] AS cheapest_store,
    (ARRAY_AGG(f.store_slug ORDER BY f.price_khr DESC))[1] AS most_expensive_store
FROM silver.fct_daily_prices f
JOIN silver.canonical_items ci ON ci.item_id::text = f.item_id
LEFT JOIN silver.dim_items di ON di.item_id = f.item_id
WHERE f.cpi_eligible = TRUE
  AND coalesce(f.is_outlier, FALSE) = FALSE
GROUP BY f.scrape_date, f.item_id, ci.canonical_name, di.brand, di.coicop_division, di.coicop_code
HAVING count(DISTINCT f.store_slug) >= 2;

-- 2. Promotional Volatility & Discount Analytics View
CREATE OR REPLACE VIEW silver.v_promo_analytics AS
SELECT 
    f.scrape_date,
    f.store_slug,
    f.coicop_division,
    count(*) AS total_scraped_items,
    count(CASE WHEN f.on_promo THEN 1 END) AS promo_items_count,
    round((count(CASE WHEN f.on_promo THEN 1 END)::numeric / count(*)) * 100.0, 2) AS promo_penetration_pct,
    round(avg(CASE WHEN f.on_promo THEN f.discount_pct END), 2) AS avg_discount_pct,
    round(avg(f.price_khr), 2) AS avg_shelf_price_khr,
    round(avg(coalesce(f.original_price_khr, f.price_khr)), 2) AS avg_regular_price_khr,
    round(
        (1.0 - (avg(f.price_khr) / nullif(avg(coalesce(f.original_price_khr, f.price_khr)), 0))) * 100.0,
        2
    ) AS promo_deflation_savings_pct
FROM silver.fct_daily_prices f
WHERE f.cpi_eligible = TRUE
  AND coalesce(f.is_outlier, FALSE) = FALSE
GROUP BY f.scrape_date, f.store_slug, f.coicop_division;

-- 3. Automated Monthly Partition Maintenance Procedure
CREATE OR REPLACE PROCEDURE silver.sp_create_monthly_partitions(months_ahead INT DEFAULT 6)
LANGUAGE plpgsql
AS $$
DECLARE
    start_dt DATE;
    end_dt DATE;
    part_name TEXT;
    sql_stmt TEXT;
    i INT;
BEGIN
    FOR i IN 0..months_ahead LOOP
        start_dt := date_trunc('month', CURRENT_DATE + (i || ' month')::INTERVAL)::DATE;
        end_dt := (date_trunc('month', CURRENT_DATE + ((i + 1) || ' month')::INTERVAL))::DATE;
        part_name := 'fct_daily_prices_y' || to_char(start_dt, 'YYYY') || 'm' || to_char(start_dt, 'MM');

        -- Check if fct_daily_prices is a partitioned table
        IF EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'silver' AND c.relname = 'fct_daily_prices' AND c.relkind = 'p'
        ) THEN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'silver' AND c.relname = part_name
            ) THEN
                sql_stmt := format(
                    'CREATE TABLE IF NOT EXISTS silver.%I PARTITION OF silver.fct_daily_prices FOR VALUES FROM (%L) TO (%L);',
                    part_name, start_dt, end_dt
                );
                EXECUTE sql_stmt;
                RAISE NOTICE 'Created partition silver.% for range [%, %)', part_name, start_dt, end_dt;
            END IF;
        END IF;
    END LOOP;
END;
$$;
