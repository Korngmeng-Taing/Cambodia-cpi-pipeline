"""
tests/test_dbt_connection.py
────────────────────────────
Integration test verifying PostgreSQL connection and Bronze/Silver/Gold schemas.
"""

import os

import psycopg2


def test_postgres_connection_and_schemas():
    host = os.getenv("DB_HOST", "localhost")
    # In docker containers, DB_HOST=postgres; on local host machine, localhost
    try:
        conn = psycopg2.connect(
            host=host,
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "cpi_user"),
            password=os.getenv("DB_PASS", "cpi_pass"),
            dbname=os.getenv("DB_NAME", "cpi_db"),
        )
    except psycopg2.OperationalError:
        # Fallback to postgres if localhost fails (or vice versa)
        alt_host = "postgres" if host == "localhost" else "localhost"
        conn = psycopg2.connect(
            host=alt_host,
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "cpi_user"),
            password=os.getenv("DB_PASS", "cpi_pass"),
            dbname=os.getenv("DB_NAME", "cpi_db"),
        )

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

        # Verify hello world bronze model
        cur.execute("SELECT message, layer, status FROM bronze.stg_hello_world;")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "hello_world"
        assert row[1] == "bronze"
        assert row[2] == "connection_verified"

    conn.close()
