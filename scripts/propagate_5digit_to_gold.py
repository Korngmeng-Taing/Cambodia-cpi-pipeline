"""
scripts/propagate_5digit_to_gold.py
───────────────────────────────────
Propagates the UN COICOP 2018 5-digit codes from silver.canonical_items
into gold.dim_item_base_prices and gold.fct_elementary_indices.
"""
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from pipeline.config import get_database_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("propagate_5digit")

SQL_PROPAGATE = """
-- 1. Update gold.dim_item_base_prices
UPDATE gold.dim_item_base_prices b
SET coicop_code = c.coicop_code,
    coicop_division = c.coicop_division
FROM silver.canonical_items c
WHERE b.item_id = c.item_id::text
  AND b.coicop_code != c.coicop_code;

-- 2. Update gold.fct_elementary_indices
UPDATE gold.fct_elementary_indices e
SET coicop_code = c.coicop_code,
    coicop_division = c.coicop_division
FROM silver.canonical_items c
WHERE e.item_id = c.item_id::text
  AND e.coicop_code != c.coicop_code;
"""

def main():
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    conn_str = conn_str.replace("@postgres:", "@localhost:")

    log.info("Connecting to PostgreSQL to propagate 5-digit COICOP codes to gold tables...")
    conn = psycopg2.connect(conn_str)
    try:
        with conn.cursor() as cur:
            log.info("Updating gold.dim_item_base_prices and gold.fct_elementary_indices...")
            cur.execute("""
                UPDATE gold.dim_item_base_prices b
                SET coicop_code = c.coicop_code,
                    coicop_division = c.coicop_division
                FROM silver.canonical_items c
                WHERE b.item_id = c.item_id::text
                  AND b.coicop_code != c.coicop_code;
            """)
            dim_updated = cur.rowcount
            log.info(f"✅ Updated {dim_updated:,} items in gold.dim_item_base_prices")

            cur.execute("""
                UPDATE gold.fct_elementary_indices e
                SET coicop_code = c.coicop_code,
                    coicop_division = c.coicop_division
                FROM silver.canonical_items c
                WHERE e.item_id = c.item_id::text
                  AND e.coicop_code != c.coicop_code;
            """)
            fct_updated = cur.rowcount
            log.info(f"✅ Updated {fct_updated:,} items in gold.fct_elementary_indices from canonical")

            cur.execute("""
                UPDATE gold.fct_elementary_indices
                SET coicop_code = CASE
                    WHEN coicop_code = '01.1.1' THEN '01.1.1.9'
                    WHEN coicop_code = '01.1.2' THEN '01.1.2.9'
                    WHEN coicop_code = '01.1.3' THEN '01.1.3.1'
                    WHEN coicop_code = '01.1.4' THEN '01.1.4.3'
                    WHEN coicop_code = '01.1.5' THEN '01.1.5.1'
                    WHEN coicop_code = '01.1.6' THEN '01.1.6.1'
                    WHEN coicop_code = '01.1.7' THEN '01.1.7.2'
                    WHEN coicop_code = '01.1.8' THEN '01.1.8.4'
                    WHEN coicop_code = '01.1.9' THEN '01.1.9.9'
                    WHEN coicop_code = '01.2.1' THEN '01.2.1.1'
                    WHEN coicop_code = '01.2.2' THEN '01.2.2.2'
                    WHEN coicop_code = '02.1.1' THEN '02.1.1.1'
                    WHEN coicop_code = '02.1.2' THEN '02.1.2.1'
                    WHEN coicop_code = '02.1.3' THEN '02.1.3.1'
                    WHEN coicop_code IN ('02.2.0', '02.2.1') THEN '02.2.0.1'
                    WHEN coicop_code ~ '^[0-9]{2}\\.[0-9]\\.[0-9]$' THEN coicop_code || '.1'
                    ELSE coicop_code
                END
                WHERE LENGTH(coicop_code) - LENGTH(REPLACE(coicop_code, '.', '')) = 2;
            """)
            residual_updated = cur.rowcount
            log.info(f"✅ Upgraded {residual_updated:,} residual 4-digit items in gold.fct_elementary_indices to 5-digit")

            conn.commit()
            log.info("All transactions committed successfully!")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
