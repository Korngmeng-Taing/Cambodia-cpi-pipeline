"""
scripts/upgrade_canonical_to_5digit.py
──────────────────────────────────────
Enriches silver.canonical_items with UN COICOP 2018 5-digit codes
using high-precision keyword patterns for Rice, Bread, Noodles, Pork, Beef,
Poultry, Fish, Seafood, Dairy, and Automotive Fuels.
"""
import sys
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from pipeline.config import get_database_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("upgrade_5digit")

SQL_UPGRADE = """
UPDATE silver.canonical_items
SET coicop_code = CASE 
    -- 01.1.1 Bread and cereals
    WHEN coicop_code = '01.1.1' AND canonical_name ~* '(rice|អង្ករ|jasmine|phka|glutinous|basmati)' THEN '01.1.1.1'
    WHEN coicop_code = '01.1.1' AND canonical_name ~* '(bread|baguette|croissant|sandwich|toast|brioche|នំប៉័ង)' THEN '01.1.1.2'
    WHEN coicop_code = '01.1.1' AND canonical_name ~* '(noodle|pasta|spaghetti|macaroni|ramen|vermicelli|udon|soba|មី|គុយទាវ)' THEN '01.1.1.3'
    WHEN coicop_code = '01.1.1' AND canonical_name ~* '(biscuit|cracker|cookie|wafer|oreo|ritz|នំស្រួយ)' THEN '01.1.1.4'
    WHEN coicop_code = '01.1.1' AND canonical_name ~* '(cake|pastry|muffin|pie|tart|donut|doughnut|waffle|pancake)' THEN '01.1.1.5'
    WHEN coicop_code = '01.1.1' AND canonical_name ~* '(flour|oat|cereal|cornflake|muesli|granola|ម្សៅ)' THEN '01.1.1.9'

    -- 01.1.2 Meat
    WHEN coicop_code = '01.1.2' AND canonical_name ~* '(pork|pig|bacon|ham|lard|ribs|belly|សាច់ជ្រូក)' THEN '01.1.2.1'
    WHEN coicop_code = '01.1.2' AND canonical_name ~* '(beef|steak|veal|bovine|angus|wagyu|សាច់គោ)' THEN '01.1.2.2'
    WHEN coicop_code = '01.1.2' AND canonical_name ~* '(chicken|poultry|wing|breast|drumstick|សាច់មាន់)' THEN '01.1.2.3'
    WHEN coicop_code = '01.1.2' AND canonical_name ~* '(duck|goose|សាច់ទា)' THEN '01.1.2.4'
    WHEN coicop_code = '01.1.2' AND canonical_name ~* '(sausage|hotdog|salami|meatball|paté|pate|សាច់ក្រក)' THEN '01.1.2.5'

    -- 01.1.3 Fish & Seafood
    WHEN coicop_code = '01.1.3' AND canonical_name ~* '(salmon|tuna|tilapia|snapper|catfish|mackerel|bass|cod|trout|fish|ត្រី)' THEN '01.1.3.1'
    WHEN coicop_code = '01.1.3' AND canonical_name ~* '(shrimp|prawn|crab|squid|octopus|lobster|mussel|clam|oyster|scallop|បង្គា|ក្តាម|មឹក)' THEN '01.1.3.2'
    WHEN coicop_code = '01.1.3' AND canonical_name ~* '(prahok|canned fish|sardine|dried fish|fish sauce|smoked fish|ប្រហុក|ត្រីងៀត|ត្រីខ)' THEN '01.1.3.3'

    -- 01.1.4 Milk, Cheese & Eggs
    WHEN coicop_code = '01.1.4' AND canonical_name ~* '(egg|eggs|ពងមាន់|ពងទា)' THEN '01.1.4.1'
    WHEN coicop_code = '01.1.4' AND canonical_name ~* '(cheese|cheddar|mozzarella|parmesan|brie|gouda|ឈីស)' THEN '01.1.4.3'
    WHEN coicop_code = '01.1.4' AND canonical_name ~* '(milk|yogurt|yoghurt|butter|cream|dairy|ទឹកដោះគោ)' THEN '01.1.4.3'

    -- 07.2.2 Fuels
    WHEN coicop_code = '07.2.2' AND canonical_name ~* '(gasoline|petrol|super|regular|ron|សាំង)' THEN '07.2.2.1'
    WHEN coicop_code = '07.2.2' AND canonical_name ~* '(diesel|gasoil|ម៉ាស៊ូត)' THEN '07.2.2.2'

    ELSE coicop_code
END
WHERE coicop_code IN ('01.1.1', '01.1.2', '01.1.3', '01.1.4', '07.2.2');
"""

def main():
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    # If on host machine, use localhost
    conn_str = conn_str.replace("@postgres:", "@localhost:")
    
    log.info("Connecting to PostgreSQL to upgrade canonical items to 5-digit COICOP 2018...")
    conn = psycopg2.connect(conn_str)
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_UPGRADE)
            affected = cur.rowcount
            conn.commit()
            log.info(f"✅ Successfully updated {affected:,} canonical items in silver.canonical_items!")
            
            # Print updated distribution
            cur.execute("""
                SELECT coicop_code, COUNT(*) as cnt
                FROM silver.canonical_items
                WHERE length(coicop_code) = 8
                GROUP BY coicop_code
                ORDER BY cnt DESC;
            """)
            rows = cur.fetchall()
            log.info(f"📊 Total 5-digit categories created: {len(rows)}")
            for r in rows[:15]:
                log.info(f"   • {r[0]}: {r[1]:,} items")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
