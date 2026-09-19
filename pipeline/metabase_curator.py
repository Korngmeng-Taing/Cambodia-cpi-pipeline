"""
pipeline/metabase_curator.py
────────────────────────────
Automated Metabase catalog curation:
Hides raw monthly partition tables and internal pipeline tables so end users
and analysts only see curated, analytics-ready Gold facts, dimensions, and views.
"""

from __future__ import annotations

import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)

INTERNAL_TABLES = [
    ("bronze", "raw_prices"),
    ("bronze", "scrape_errors"),
    ("ops", "circuit_breaker_events"),
    ("ops", "cold_storage_catalog"),
    ("silver", "canonical_item_barcodes"),
    ("silver", "dim_canonical_products"),
    ("silver", "gold_standard_items"),
    ("silver", "classification_ground_truth"),
    ("silver", "coicop_critical_traps"),
    ("silver", "store_purity"),
    ("silver", "manual_item_corrections"),
    ("silver", "macro_indicators"),
    ("gold", "cpi_base_dates"),
    ("gold", "nis_official_cpi"),
    ("gold", "fct_elementary_indices"),
]


def get_metabase_connection():
    """Establishes connection to Metabase application database."""
    hosts = [
        os.environ.get("METABASE_DB_HOST"),
        os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "postgres",
        "localhost",
        "127.0.0.1",
    ]
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    user = os.environ.get("MB_DB_USER", "metabase")
    password = os.environ.get("MB_DB_PASS", "metabase")
    dbname = os.environ.get("MB_DB_NAME", "metabase")

    for h in [h for h in hosts if h]:
        try:
            conn = psycopg2.connect(
                host=h,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=3,
            )
            return conn
        except Exception:
            continue
    raise RuntimeError(f"Could not connect to Metabase database on any candidate host: {hosts}")


def curate_metabase_catalog(db_id: int = 2) -> dict:
    """Hides raw monthly partition tables and internal pipeline tables in Metabase."""
    conn = get_metabase_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Hide all partition tables
            cur.execute("""
                UPDATE metabase_table
                SET visibility_type = 'hidden'
                WHERE db_id = %s 
                  AND (name LIKE '%%_202%%' OR name LIKE '%%_default')
                  AND (visibility_type IS NULL OR visibility_type != 'hidden');
            """, (db_id,))
            partitions_hidden = cur.rowcount

            # 2. Hide internal pipeline/support tables
            internal_hidden = 0
            for schema, name in INTERNAL_TABLES:
                cur.execute("""
                    UPDATE metabase_table
                    SET visibility_type = 'hidden'
                    WHERE db_id = %s AND schema = %s AND name = %s
                      AND (visibility_type IS NULL OR visibility_type != 'hidden');
                """, (db_id, schema, name))
                internal_hidden += cur.rowcount

            conn.commit()

            # 3. Query remaining visible tables
            cur.execute("""
                SELECT schema, name
                FROM metabase_table
                WHERE db_id = %s AND active = true AND visibility_type IS NULL
                ORDER BY schema, name;
            """, (db_id,))
            visible_tables = [f"{r['schema']}.{r['name']}" for r in cur.fetchall()]

            log.info(
                "Curated Metabase catalog: %d partitions hidden, %d internal tables hidden, %d visible analytical tables remaining.",
                partitions_hidden,
                internal_hidden,
                len(visible_tables),
            )
            return {
                "partitions_hidden": partitions_hidden,
                "internal_hidden": internal_hidden,
                "visible_tables_count": len(visible_tables),
                "visible_tables": visible_tables,
            }
    finally:
        conn.close()
