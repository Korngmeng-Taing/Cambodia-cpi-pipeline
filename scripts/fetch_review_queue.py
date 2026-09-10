"""
scripts/fetch_review_queue.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT item_id, canonical_name, coicop_division, coicop_code
        FROM silver.canonical_items
        WHERE coicop_method = 'human_review_required'
        LIMIT 20;
    """)
    rows = cur.fetchall()
    for row in rows:
        print(f"{row[0]}|{row[1]}|{row[2]}|{row[3]}")
    conn.close()

if __name__ == "__main__":
    main()
