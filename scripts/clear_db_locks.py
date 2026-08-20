import os
import sys

sys.path.insert(0, os.path.abspath("."))
from pipeline.config import get_db_connection


def clear_db_locks():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE pid <> pg_backend_pid()
              AND datname = 'cpi_db'
              AND state IN ('active', 'idle in transaction');
        """)
        terminated = cur.fetchall()
        print(f"Terminated {len(terminated)} blocking processes.")

if __name__ == "__main__":
    clear_db_locks()
