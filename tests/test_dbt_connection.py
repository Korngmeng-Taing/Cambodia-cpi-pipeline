"""
tests/test_dbt_connection.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Integration test verifying PostgreSQL connection and Bronze/Silver/Gold schemas.
"""

from __future__ import annotations

import os

import psycopg2
import pytest


def test_postgres_connection_and_schemas():
    host = os.getenv("DB_HOST", "localhost")
    # In docker containers, DB_HOST=postgres; on local host machine, localhost
    try:
        conn = psycopg2.connect(
            host=host,
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASS", ""),
            dbname=os.getenv("DB_NAME", "cpi_db"),
        )
    except psycopg2.OperationalError:
        try:
            alt_host = "postgres" if host == "localhost" else "localhost"
            conn = psycopg2.connect(
                host=alt_host,
                port=int(os.getenv("DB_PORT", "5432")),
                user=os.getenv("DB_USER", ""),
                password=os.getenv("DB_PASS", ""),
                dbname=os.getenv("DB_NAME", "cpi_db"),
            )
        except psycopg2.OperationalError as e:
            pytest.skip(f"Postgres database not reachable: {e}")

    with conn.cursor() as cur:
        # Verify required medallion schemas exist
        cur.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name IN ('bronze', 'staging', 'silver', 'gold');
        """
        )
        schemas = {row[0] for row in cur.fetchall()}
        assert "bronze" in schemas
        assert "silver" in schemas
        assert "gold" in schemas

        # Verify bronze table accessible
        cur.execute("SELECT COUNT(*) FROM bronze.raw_prices;")
        count = cur.fetchone()[0]
        assert count >= 0

    conn.close()
