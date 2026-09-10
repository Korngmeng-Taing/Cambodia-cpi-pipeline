"""
scripts/create_table.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import get_db_connection

conn = get_db_connection()
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS silver.manual_item_corrections (
        item_id UUID PRIMARY KEY,
        canonical_name TEXT,
        coicop_division TEXT,
        coicop_code TEXT,
        corrected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
""")
conn.commit()
conn.close()
print("Table silver.manual_item_corrections created successfully.")
