import logging
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("audit_classification")

def audit():
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Housing Anomaly (Low Price)
    log.info("Checking for Housing anomalies (Low Price < 50,000 KHR)...")
    try:
        cur.execute("""
            SELECT s.item_id, ci.canonical_name, s.unit_price_khr 
            FROM silver.clean_store_prices s
            JOIN silver.canonical_items ci ON s.item_id::text = ci.item_id::text
            WHERE s.coicop_division = '04' AND s.unit_price_khr < 50000 
            LIMIT 10;
        """)
        housing_anomalies = cur.fetchall()
        for row in housing_anomalies:
            log.warning(f"Housing Anomaly: {row[1]} | Price: {row[2]} KHR")
    except Exception as e:
        log.error(f"Error checking housing: {e}")

    # 2. Food Anomaly (High Price)
    log.info("Checking for Food anomalies (High Price > 1,000,000 KHR)...")
    try:
        cur.execute("""
            SELECT s.item_id, ci.canonical_name, s.unit_price_khr 
            FROM silver.clean_store_prices s
            JOIN silver.canonical_items ci ON s.item_id::text = ci.item_id::text
            WHERE s.coicop_division = '01' AND s.unit_price_khr > 1000000 
            LIMIT 10;
        """)
        food_anomalies = cur.fetchall()
        for row in food_anomalies:
            log.warning(f"Food Anomaly: {row[1]} | Price: {row[2]} KHR")
    except Exception as e:
        log.error(f"Error checking food: {e}")

    # 3. Low Confidence Items
    log.info("Checking for low confidence classifications (< 0.5)...")
    try:
        cur.execute("""
            SELECT item_id, canonical_name, coicop_division, coicop_confidence 
            FROM silver.canonical_items 
            WHERE coicop_confidence < 0.5 
            LIMIT 10;
        """)
        low_conf = cur.fetchall()
        for row in low_conf:
            log.warning(f"Low Conf: {row[1]} | Div: {row[2]} | Conf: {row[3]}")
    except Exception as e:
        log.error(f"Error checking confidence: {e}")

    # 4. Sample check by division
    log.info("Sampling products from each division...")
    try:
        cur.execute("SELECT DISTINCT coicop_division FROM silver.canonical_items ORDER BY 1")
        divisions = [row[0] for row in cur.fetchall()]
        for div in divisions:
            cur.execute("""
                SELECT canonical_name 
                FROM silver.canonical_items 
                WHERE coicop_division = %s 
                LIMIT 3;
            """, (div,))
            samples = cur.fetchall()
            log.info(f"Division {div} Samples: {[s[0] for s in samples]}")
    except Exception as e:
        log.error(f"Error sampling divisions: {e}")

    conn.close()

if __name__ == "__main__":
    audit()
