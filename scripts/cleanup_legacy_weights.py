"""
scripts/cleanup_legacy_weights.py
Drops legacy gold.category_weights table and re-points gold.coicop_weights
view directly to gold.cambodia_cpi_coicop_weights_breakdown.
"""
import logging
from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cleanup_legacy_weights")

def cleanup():
    conn = get_db_connection()
    cur = conn.cursor()

    logger.info("Re-pointing gold.coicop_weights view to gold.cambodia_cpi_coicop_weights_breakdown...")
    cur.execute("""
        CREATE OR REPLACE VIEW gold.coicop_weights AS
        SELECT 
            coicop_code AS coicop_division,
            coicop_name AS division_name,
            weight_pct,
            source,
            '2026-08-01'::date AS effective_date
        FROM gold.cambodia_cpi_coicop_weights_breakdown
        WHERE coicop_level = 'Division'
        ORDER BY coicop_code;
    """)

    logger.info("Dropping legacy gold.category_weights table if exists...")
    cur.execute("DROP TABLE IF EXISTS gold.category_weights CASCADE;")

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Successfully cleaned up legacy weights tables.")

if __name__ == "__main__":
    cleanup()
