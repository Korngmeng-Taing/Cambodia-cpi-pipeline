import logging
import psycopg2
from psycopg2.extras import execute_values
from pipeline.hierarchical_classifier import HierarchicalCOICOPClassifier
from pipeline.config import get_db_connection
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_item(classifier, item):
    """Worker function to classify a single item."""
    item_id, store_slug, name = item
    try:
        code, method, confidence = classifier.classify(item_id, name, store_slug)
        return (item_id, code, method, confidence)
    except Exception as e:
        logger.error(f"Error classifying {item_id}: {e}")
        return None

def main():
    # 1. Initialize Classifier
    classifier = HierarchicalCOICOPClassifier(
        hierarchy_path="coicop_hierarchy.json"
    )

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 2. Identify items that need classification
            logger.info("Fetching items for classification...")
            cur.execute("""
                SELECT item_id, store_slug, canonical_name
                FROM silver.int_coicop_classified
                WHERE coicop_method IN ('unclassified', 'review')
                   OR coicop_confidence < 0.8
            """)
            items = cur.fetchall()
            logger.info(f"Found {len(items)} items needing classification.")

            if not items:
                logger.info("No items to classify. Exiting.")
                return

            # 3. Process items in parallel
            updates = []
            max_workers = 10 # Process 10 items at once to avoid hitting rate limits too hard
            logger.info(f"Starting parallel classification with {max_workers} workers...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all items to the executor
                future_to_item = {executor.submit(process_item, classifier, item): item for item in items}

                for future in as_completed(future_to_item):
                    result = future.result()
                    if result:
                        updates.append(result)

                    if len(updates) % 50 == 0 and len(updates) > 0:
                        logger.info(f"Processed {len(updates)}/{len(items)} items...")

            # 4. Bulk update the cache
            if updates:
                logger.info(f"Updating cache with {len(updates)} results...")
                execute_values(cur, """
                    INSERT INTO silver.classification_cache (item_id, coicop_code, coicop_division, coicop_method, confidence)
                    VALUES %s
                    ON CONFLICT (item_id) DO UPDATE SET
                        coicop_code = EXCLUDED.coicop_code,
                        coicop_division = EXCLUDED.coicop_division,
                        coicop_method = EXCLUDED.coicop_method,
                        confidence = EXCLUDED.confidence,
                        classified_at = CURRENT_TIMESTAMP
                """, [
                    (u[0], u[1], u[1].split('.')[0] if '.' in u[1] else u[1], u[2], u[3]) for u in updates
                ])
                conn.commit()
                logger.info("Cache updated successfully.")

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
