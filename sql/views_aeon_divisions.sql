-- View: AEON Product Distribution by COICOP Division
-- Run this in the database to create a queryable view

CREATE OR REPLACE VIEW gold.vw_aeon_product_divisions AS
WITH classified_products AS (
    SELECT
        ci.item_id,
        ci.canonical_name,
        ci.brand,
        ci.barcode,
        ci.size_norm,
        COALESCE(cs.coicop_division, 'UNCLASSIFIED') AS coicop_division,
        COALESCE(cs.coicop_code, cs.coicop_division, 'UNCLASSIFIED') AS coicop_code,
        CASE
            WHEN cs.coicop_division = '01' THEN 'Food & Non-Alcoholic Beverages'
            WHEN cs.coicop_division = '02' THEN 'Alcoholic Beverages & Tobacco'
            WHEN cs.coicop_division = '03' THEN 'Clothing & Footwear'
            WHEN cs.coicop_division = '04' THEN 'Housing, Water, Electricity, Gas'
            WHEN cs.coicop_division = '05' THEN 'Furnishings, Household Equipment'
            WHEN cs.coicop_division = '06' THEN 'Health'
            WHEN cs.coicop_division = '07' THEN 'Transport'
            WHEN cs.coicop_division = '08' THEN 'Communication'
            WHEN cs.coicop_division = '09' THEN 'Recreation & Culture'
            WHEN cs.coicop_division = '10' THEN 'Education'
            WHEN cs.coicop_division = '11' THEN 'Restaurants & Hotels'
            WHEN cs.coicop_division = '12' THEN 'Miscellaneous Goods & Services'
            ELSE 'UNCLASSIFIED'
        END AS division_name,
        fdp.store_slug,
        fdp.scrape_date,
        fdp.unit_price_khr,
        fdp.size_value,
        fdp.size_unit
    FROM silver.canonical_items ci
    LEFT JOIN (
        SELECT DISTINCT ON (item_id)
            item_id AS item_id,
            coicop_division,
            coicop_code
        FROM silver.int_coicop_classified
        ORDER BY item_id,
                 CASE WHEN coicop_division <> 'UNCLASSIFIED' THEN 1 ELSE 2 END,
                 coicop_confidence DESC
    ) cs ON cs.item_id = ci.item_id::text
    JOIN gold.fct_daily_prices fdp ON fdp.item_id = ci.item_id::text
    WHERE fdp.store_slug IN ('aeon', 'aeon3')
)
SELECT * FROM classified_products;


-- Query 1: AEON division summary
SELECT
    coicop_division,
    division_name,
    COUNT(DISTINCT canonical_name) AS product_count,
    ROUND(AVG(unit_price_khr), 2) AS avg_price_khr,
    MIN(unit_price_khr) AS min_price,
    MAX(unit_price_khr) AS max_price,
    ROUND(
        COUNT(DISTINCT canonical_name)::numeric / 
        SUM(COUNT(DISTINCT canonical_name)) OVER () * 100, 1
    ) AS pct_of_total
FROM gold.vw_aeon_product_divisions
WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.vw_aeon_product_divisions)
GROUP BY coicop_division, division_name
ORDER BY coicop_division;


-- Query 2: Sample products per division
SELECT
    coicop_division,
    division_name,
    canonical_name,
    brand,
    size_norm,
    unit_price_khr,
    store_slug
FROM gold.vw_aeon_product_divisions
WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.vw_aeon_product_divisions)
ORDER BY coicop_division, canonical_name
LIMIT 100;


-- Query 3: Division comparison between aeon and aeon3
SELECT
    store_slug,
    coicop_division,
    division_name,
    COUNT(DISTINCT canonical_name) AS product_count
FROM gold.vw_aeon_product_divisions
WHERE scrape_date = (SELECT MAX(scrape_date) FROM gold.vw_aeon_product_divisions)
GROUP BY store_slug, coicop_division, division_name
ORDER BY store_slug, coicop_division;
