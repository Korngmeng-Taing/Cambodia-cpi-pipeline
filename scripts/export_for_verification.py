import psycopg2
import csv
import logging
from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    conn = get_db_connection()
    output_file = "products_for_verification.csv"
    
    try:
        with conn.cursor() as cur:
            logger.info("Identifying products for gold standard verification...")
            
            # Strategic Query:
            # 1. All 'review' or 'unclassified' items
            # 2. Low confidence items (< 0.7)
            # 3. Stratified sample: 50 items from each division to ensure coverage
            query = """
                (
                    -- Low confidence or unclassified
                    SELECT item_id, canonical_name, coicop_code, coicop_method, coicop_confidence
                    FROM silver.int_coicop_classified
                    WHERE coicop_method IN ('review', 'unclassified')
                       OR coicop_confidence < 0.7
                )
                UNION
                (
                    -- Stratified Sample: 50 random items per division
                    SELECT item_id, canonical_name, coicop_code, coicop_method, coicop_confidence
                    FROM (
                        SELECT item_id, canonical_name, coicop_code, coicop_method, coicop_confidence,
                                ROW_NUMBER() OVER (PARTITION BY split_part(coicop_code, '.', 1) ORDER BY random()) as rn
                        FROM silver.int_coicop_classified
                    ) s
                    WHERE rn <= 50
                )
                ORDER BY coicop_confidence ASC;
            """
            
            cur.execute(query)
            rows = cur.fetchall()
            
            logger.info(f"Found {len(rows)} items to export.")
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Header for the human reviewer
                writer.writerow(['item_id', 'product_name', 'current_ai_code', 'current_method', 'confidence', 'GOLD_CODE_VERIFIED'])
                
                for row in rows:
                    # row: (item_id, name, code, method, conf)
                    writer.writerow([row[0], row[1], row[2], row[3], row[4], ''])
                    
            logger.info(f"Export complete. Please verify the items in: {output_file}")

    except Exception as e:
        logger.error(f"Export failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
