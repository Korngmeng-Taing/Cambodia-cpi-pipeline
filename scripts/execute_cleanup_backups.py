"""
scripts/execute_cleanup_backups.py
──────────────────────────────────
Executes Migration 0005: Drops obsolete migration backup tables
(bronze.raw_prices_unpartitioned_backup and silver.clean_store_prices_unpartitioned_backup)
to reclaim ~2.18 GB of active PostgreSQL disk space.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import get_db_connection


def main():
    print("Connecting to cpi_db...")
    conn = get_db_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            migration_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "sql",
                "migrations",
                "0005_drop_unpartitioned_backups.sql",
            )
            with open(migration_path, "r", encoding="utf-8") as f:
                sql = f.read()

            print("Executing migration 0005_drop_unpartitioned_backups.sql...")
            cur.execute(sql)
            print("Successfully dropped obsolete unpartitioned backup tables!")

            # Verify size
            cur.execute("""
                SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as total_size
                FROM pg_tables
                WHERE schemaname IN ('bronze', 'silver', 'gold', 'staging')
                ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
                LIMIT 10;
            """)
            rows = cur.fetchall()
            print("\nTop 10 active tables by size after cleanup:")
            for schema, table, size in rows:
                print(f"  - {schema}.{table}: {size}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
