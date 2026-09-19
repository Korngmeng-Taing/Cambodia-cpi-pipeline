"""
scripts/check_schema.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import get_db_connection

conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'silver' AND table_name = 'coicop_override_manual';")
cols = [row[0] for row in cur.fetchall()]
print(f"Columns in silver.coicop_override_manual: {cols}")
conn.close()
