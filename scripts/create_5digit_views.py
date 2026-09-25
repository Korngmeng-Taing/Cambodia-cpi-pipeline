"""
scripts/create_5digit_views.py
──────────────────────────────
Creates analytical views in the Gold schema to expose 5-digit UN COICOP 2018
sub-indices (Rice, Fresh Meat, Fish, Dairy, Automotive Fuels) for empirical
thesis research and Metabase dashboards.
"""
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from pipeline.config import get_database_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("create_5digit_views")

SQL_CREATE_VIEWS = """
-- 1. Daily 5-Digit Subclass Jevons Micro-Index View
CREATE OR REPLACE VIEW gold.v_cpi_subclass_5digit_daily AS
SELECT 
    calculation_date,
    coicop_division,
    coicop_code,
    CASE 
        WHEN coicop_code = '01.1.1.1' THEN 'Rice'
        WHEN coicop_code = '01.1.1.2' THEN 'Bread'
        WHEN coicop_code = '01.1.1.3' THEN 'Pasta & Noodles'
        WHEN coicop_code = '01.1.1.4' THEN 'Biscuits & Cookies'
        WHEN coicop_code = '01.1.1.5' THEN 'Pastries & Cakes'
        WHEN coicop_code = '01.1.1.9' THEN 'Other Cereals & Flour'
        WHEN coicop_code = '01.1.2.1' THEN 'Fresh Pork'
        WHEN coicop_code = '01.1.2.2' THEN 'Fresh Beef'
        WHEN coicop_code = '01.1.2.3' THEN 'Fresh Poultry & Chicken'
        WHEN coicop_code = '01.1.2.4' THEN 'Fresh Duck'
        WHEN coicop_code = '01.1.2.5' THEN 'Processed Meat & Sausages'
        WHEN coicop_code = '01.1.3.1' THEN 'Fresh Fish'
        WHEN coicop_code = '01.1.3.2' THEN 'Seafood (Shrimp, Crab, Squid)'
        WHEN coicop_code = '01.1.3.3' THEN 'Processed Fish & Prahok'
        WHEN coicop_code = '01.1.4.1' THEN 'Fresh Eggs'
        WHEN coicop_code = '01.1.4.2' THEN 'Processed Eggs'
        WHEN coicop_code = '01.1.4.3' THEN 'Dairy Products'
        WHEN coicop_code = '01.1.5.1' THEN 'Cooking & Vegetable Oils'
        WHEN coicop_code = '01.1.5.2' THEN 'Animal Fats & Margarine'
        WHEN coicop_code = '01.1.6.1' THEN 'Fresh Fruit'
        WHEN coicop_code = '01.1.6.2' THEN 'Dried Fruit'
        WHEN coicop_code = '01.1.6.3' THEN 'Nuts & Seeds'
        WHEN coicop_code = '01.1.7.1' THEN 'Leaf & Stem Vegetables'
        WHEN coicop_code = '01.1.7.2' THEN 'Fruit Vegetables'
        WHEN coicop_code = '01.1.7.3' THEN 'Root Vegetables'
        WHEN coicop_code = '01.1.7.4' THEN 'Tubers & Starchy Roots'
        WHEN coicop_code = '01.1.7.5' THEN 'Legumes & Pulses'
        WHEN coicop_code = '01.1.7.6' THEN 'Preserved Vegetables'
        WHEN coicop_code = '01.1.8.1' THEN 'Sugar & Sweeteners'
        WHEN coicop_code = '01.1.8.2' THEN 'Jam & Honey'
        WHEN coicop_code = '01.1.8.3' THEN 'Chocolate Confectionery'
        WHEN coicop_code = '01.1.8.4' THEN 'Non-Chocolate Confectionery'
        WHEN coicop_code = '01.1.8.5' THEN 'Ice Cream'
        WHEN coicop_code = '01.1.9.1' THEN 'Sauces, Spices & Condiments'
        WHEN coicop_code = '01.1.9.2' THEN 'Baby Food'
        WHEN coicop_code = '01.1.9.9' THEN 'Ready Meals & Snacks'
        WHEN coicop_code = '01.2.1.1' THEN 'Coffee'
        WHEN coicop_code = '01.2.1.2' THEN 'Tea'
        WHEN coicop_code = '01.2.1.3' THEN 'Cocoa & Powdered Drinks'
        WHEN coicop_code = '01.2.2.1' THEN 'Mineral & Purified Water'
        WHEN coicop_code = '01.2.2.2' THEN 'Soft Drinks & Energy Drinks'
        WHEN coicop_code = '01.2.2.3' THEN 'Fruit & Vegetable Juices'
        WHEN coicop_code = '02.1.1.1' THEN 'Spirits & Liqueurs'
        WHEN coicop_code = '02.1.2.1' THEN 'Wine'
        WHEN coicop_code = '02.1.3.1' THEN 'Beer'
        WHEN coicop_code = '02.2.0.1' THEN 'Tobacco & Cigarettes'
        WHEN coicop_code = '04.1.1.1' THEN 'Actual Rentals'
        WHEN coicop_code = '05.6.1.1' THEN 'Cleaning & Maintenance Products'
        WHEN coicop_code = '05.6.1.2' THEN 'Non-Durable Household Articles'
        WHEN coicop_code = '06.1.1.1' THEN 'Pharmaceutical Products'
        WHEN coicop_code = '06.1.2.1' THEN 'Other Medical Products'
        WHEN coicop_code = '07.2.2.1' THEN 'Automotive Gasoline'
        WHEN coicop_code = '07.2.2.2' THEN 'Automotive Diesel'
        WHEN coicop_code = '08.2.0.1' THEN 'Telephone Equipment'
        WHEN coicop_code = '09.3.1.1' THEN 'Pets & Pet Food'
        WHEN coicop_code = '12.1.3.1' THEN 'Personal Care Articles'
        ELSE coicop_code
    END as category_name,
    COUNT(*) as observation_count,
    COUNT(DISTINCT item_id) as item_count,
    ROUND(EXP(AVG(LN(price_ratio)))::numeric * 100, 3) as jevons_index,
    ROUND(AVG(price_ratio)::numeric * 100, 3) as carli_index,
    ROUND(AVG(price_ratio_pct)::numeric, 3) as avg_price_change_pct,
    COUNT(CASE WHEN is_imputed THEN 1 END) as imputed_observations
FROM gold.fct_elementary_indices
WHERE price_ratio > 0
GROUP BY calculation_date, coicop_division, coicop_code;

-- 2. Dedicated Rice Inflation Index View
CREATE OR REPLACE VIEW gold.v_cpi_rice_daily AS
SELECT 
    calculation_date,
    '01.1.1.1' as coicop_code,
    'Rice (All Varieties)' as category_name,
    6.162 as ceic_official_weight_pct,
    COUNT(*) as observation_count,
    COUNT(DISTINCT item_id) as distinct_rice_products,
    ROUND(EXP(AVG(LN(price_ratio)))::numeric * 100, 3) as rice_cpi_jevons,
    ROUND(AVG(price_ratio)::numeric * 100, 3) as rice_cpi_carli,
    ROUND(AVG(base_price_khr)::numeric, 0) as avg_base_price_khr,
    ROUND(AVG(current_price_khr)::numeric, 0) as avg_current_price_khr,
    ROUND(((EXP(AVG(LN(price_ratio))) - 1) * 100)::numeric, 3) as inflation_rate_pct
FROM gold.fct_elementary_indices
WHERE coicop_code = '01.1.1.1' AND price_ratio > 0
GROUP BY calculation_date
ORDER BY calculation_date;
"""

def main():
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    conn_str = conn_str.replace("@postgres:", "@localhost:")

    log.info("Connecting to PostgreSQL to create 5-digit COICOP 2018 analytical views...")
    conn = psycopg2.connect(conn_str)
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_CREATE_VIEWS)
            conn.commit()
            log.info("✅ Views gold.v_cpi_subclass_5digit_daily and gold.v_cpi_rice_daily created successfully!")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
