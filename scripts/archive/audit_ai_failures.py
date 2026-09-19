import logging
import pandas as pd
from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def audit_failures():
    conn = get_db_connection()
    try:
        # Join classification_cache with dim_coicop_ai_cache to get the reasoning
        query = """
            SELECT
                c.item_id,
                c.coicop_code,
                c.confidence,
                ai.reasoning,
                ci.canonical_name
            FROM silver.classification_cache c
            JOIN silver.canonical_items ci ON c.item_id::uuid = ci.item_id
            LEFT JOIN silver.dim_coicop_ai_cache ai ON lower(trim(ai.product_name)) = lower(trim(ci.canonical_name))
            WHERE c.coicop_code = 'UNCLASSIFIED'
               OR c.confidence < 0.6
            ORDER BY c.confidence ASC
        """
        df = pd.read_sql(query, conn)
        
        if df.empty:
            logger.info("No significant AI failures found in the cache.")
            return
        
        logger.info(f"Found {len(df)} items with low confidence or unclassified status.")
        print("\n--- Top AI Failures / Ambiguous Items ---")
        print(df.head(20).to_string(index=False))
        
        # Analysis of reasoning patterns
        if 'reasoning' in df.columns:
            print("\n--- Common Reasoning Patterns for Failures ---")
            print(df['reasoning'].value_counts().head(10))
            
    except Exception as e:
        logger.error(f"Audit failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    audit_failures()
