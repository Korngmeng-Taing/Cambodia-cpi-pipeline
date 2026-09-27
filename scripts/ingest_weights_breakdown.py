"""
Ingest dbt/seeds/cambodia_cpi_coicop_weights_breakdown.csv into PostgreSQL table
gold.cambodia_cpi_coicop_weights_breakdown.
"""
import csv
import logging
from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_weights")

CSV_PATH = "dbt/seeds/cambodia_cpi_coicop_weights_breakdown.csv"

def ingest():
    conn = get_db_connection()
    cur = conn.cursor()
    
    logger.info("Reading seed file: %s", CSV_PATH)
    rows = []
    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((
                r["coicop_level"],
                r["coicop_code"],
                r["coicop_name"],
                r["coicop_name_kh"],
                float(r["weight_pct"]),
                r["parent_division"],
                r["source"]
            ))
            
    logger.info("Found %d rows in CSV", len(rows))
    
    # Truncate and re-insert
    cur.execute("TRUNCATE TABLE gold.cambodia_cpi_coicop_weights_breakdown;")
    
    insert_sql = """
        INSERT INTO gold.cambodia_cpi_coicop_weights_breakdown (
            coicop_level, coicop_code, coicop_name, coicop_name_kh, weight_pct, parent_division, source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    cur.executemany(insert_sql, rows)
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Successfully ingested %d rows into gold.cambodia_cpi_coicop_weights_breakdown", len(rows))

if __name__ == "__main__":
    ingest()
