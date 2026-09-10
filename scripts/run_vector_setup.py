import logging
from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    try:
        with open('scripts/setup_vector_storage.sql', 'r') as f:
            sql = f.read()
        
        conn = get_db_connection()
        with conn.cursor() as cur:
            logger.info("Executing vector storage setup SQL...")
            cur.execute(sql)
            conn.commit()
            logger.info("Vector storage setup successfully.")
    except Exception as e:
        logger.error(f"Vector setup failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
