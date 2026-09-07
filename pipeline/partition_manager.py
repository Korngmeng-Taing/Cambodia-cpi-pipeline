"""
pipeline/partition_manager.py
──────────────────────────────
Declarative Table Partition Maintenance Manager for Cambodia CPI Pipeline.

Ensures that upcoming monthly partitions exist for high-volume partitioned tables:
  1. bronze.raw_prices (or bronze.raw_prices_part)
  2. silver.clean_store_prices (or silver.clean_store_prices_part)

Invokes the stored procedure `ops.maintain_monthly_partitions(p_months_ahead)`
or directly generates partitions if the stored procedure needs bootstrapping.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from typing import Any

from pipeline.config import get_db_connection

log = logging.getLogger(__name__)


def ensure_monthly_partitions(months_ahead: int = 3, conn: Any = None) -> dict[str, Any]:
    """Ensures monthly partitions exist for bronze and silver partitioned tables.

    Calls `ops.maintain_monthly_partitions(months_ahead)` in PostgreSQL 16.
    If the stored procedure is not yet compiled, falls back to direct DDL.

    Args:
        months_ahead: Number of future months to ensure (default: 3).
        conn: Optional existing DB connection. If None, creates a new one.

    Returns:
        dict containing status, months_maintained, and created partitions.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            # 1. Ensure ops schema exists
            cur.execute("CREATE SCHEMA IF NOT EXISTS ops;")

            # 2. Try calling stored procedure
            try:
                log.info("Executing ops.maintain_monthly_partitions(%d)...", months_ahead)
                cur.execute("CALL ops.maintain_monthly_partitions(%s);", (months_ahead,))
                conn.commit()
                log.info("Partition maintenance stored procedure executed successfully.")
                return {
                    "status": "success",
                    "method": "stored_procedure",
                    "months_ahead": months_ahead,
                }
            except Exception as proc_err:
                log.warning(
                    "ops.maintain_monthly_partitions call failed (%s). Falling back to direct DDL.",
                    proc_err,
                )
                conn.rollback()

                # Fallback: Check target tables and create partitions via Python loop
                created_partitions = []
                today = date.today()

                # Find active bronze and silver partition parents
                cur.execute(
                    """
                    SELECT n.nspname, c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname IN ('bronze', 'silver')
                      AND c.relkind = 'p'
                      AND c.relname IN ('raw_prices', 'raw_prices_part', 'clean_store_prices', 'clean_store_prices_part');
                    """
                )
                partitioned_parents = cur.fetchall()

                for i in range(months_ahead + 1):
                    # Compute year and month
                    target_month = (today.month - 1 + i) % 12 + 1
                    target_year = today.year + (today.month - 1 + i) // 12
                    next_month = target_month % 12 + 1
                    next_year = target_year if target_month < 12 else target_year + 1

                    start_date = f"{target_year:04d}-{target_month:02d}-01"
                    end_date = f"{next_year:04d}-{next_month:02d}-01"

                    for schema_name, parent_table in partitioned_parents:
                        part_name = f"{parent_table}_{target_year:04d}_{target_month:02d}"
                        ddl = f"""
                        CREATE TABLE IF NOT EXISTS {schema_name}.{part_name}
                        PARTITION OF {schema_name}.{parent_table}
                        FOR VALUES FROM ('{start_date}') TO ('{end_date}');
                        """
                        cur.execute(ddl)
                        created_partitions.append(f"{schema_name}.{part_name}")

                conn.commit()
                log.info("Direct partition fallback created/verified: %s", created_partitions)
                return {
                    "status": "success",
                    "method": "direct_ddl_fallback",
                    "months_ahead": months_ahead,
                    "partitions": created_partitions,
                }
    finally:
        if should_close:
            conn.close()


def main() -> None:
    """CLI entrypoint for standalone partition maintenance."""
    parser = argparse.ArgumentParser(description="Proactive Table Partition Maintenance")
    parser.add_argument(
        "--months",
        type=int,
        default=3,
        help="Number of future months ahead to ensure (default: 3)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = ensure_monthly_partitions(months_ahead=args.months)
    print(f"Partition maintenance result: {result}")


if __name__ == "__main__":
    main()
