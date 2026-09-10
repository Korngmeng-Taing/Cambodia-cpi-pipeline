import psycopg2
import csv
import logging
from pipeline.config import get_db_connection
from pipeline.vector_item_matcher import VectorItemMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    conn = get_db_connection()
    matcher = VectorItemMatcher()
    input_file = "products_for_verification.csv"

    try:
        with conn.cursor() as cur:
            logger.info(f"Importing verified gold classifications from {input_file}...")

            with open(input_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                import_data = []
                for row in reader:
                    gold_code = row['GOLD_CODE_VERIFIED'].strip()
                    if gold_code: # Only import if the expert actually provided a code
                        import_data.append((
                            row['item_id'],
                            row['product_name'],
                            gold_code,
                            'human_expert'
                        ))

                if not import_data:
                    logger.info("No verified codes found in CSV. Nothing to import.")
                    return

                # Bulk insert using UPSERT (On Conflict Update)
                insert_query = """
                    INSERT INTO gold.product_classification (item_id, canonical_name, gold_coicop_code, verified_by)
                    VALUES %s
                    ON CONFLICT (item_id) DO UPDATE SET
                        gold_coicop_code = EXCLUDED.gold_coicop_code,
                        verified_at = CURRENT_TIMESTAMP;
                """

                from psycopg2.extras import execute_values
                execute_values(cur, insert_query, import_data)
                conn.commit()

                logger.info(f"Successfully imported {len(import_data)} gold records.")

                # Now update embeddings for all imported items
                logger.info("Generating embeddings for gold records...")
                for item_id, name, _, _ in import_data:
                    matcher.update_gold_embedding(item_id, name)

                logger.info("Vector embeddings updated successfully.")

    except Exception as e:
        logger.error(f"Import failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
