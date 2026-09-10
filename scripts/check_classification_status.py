"""
scripts/check_classification_status.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT coicop_method, count(*) FROM silver.canonical_items GROUP BY coicop_method;")
    rows = cur.fetchall()
    for row in rows:
        print(f"{row[0]}: {row[1]}")
    conn.close()

if __name__ == "__main__":
    main()
