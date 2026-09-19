"""
Cleanup script to remove unused and deprecated tables from:
1. PostgreSQL CPI Application Database (cpi_db)
2. Metabase Metadata Database (metabase)
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_cpi_conn():
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    dbname = os.environ.get("CPI_DB_NAME", os.environ.get("DB_NAME", "cpi_db"))
    return psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)

def get_mb_conn():
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    user = os.environ.get("MB_DB_USER", "metabase")
    password = os.environ.get("MB_DB_PASS", "metabase")
    return psycopg2.connect(host=host, port=port, user=user, password=password, dbname="metabase")

def cleanup_cpi_database():
    print("=" * 70)
    print("1. CLEANING UP UNUSED TABLES IN CPI DATABASE (cpi_db)")
    print("=" * 70)
    
    tables_to_drop = [
        ("silver", "canonical_items_backup_20260911", "TABLE"),
        ("silver", "nis_official_cpi", "TABLE"),
        ("silver", "coicop_keywords", "TABLE"),
        ("silver", "canonical_items_safe", "VIEW"),
        ("gold", "product_classification", "TABLE"),
        ("staging", "macro_indicators", "TABLE")
    ]
    
    conn = get_cpi_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for schema, name, kind in tables_to_drop:
            cur.execute(f"SELECT to_regclass('{schema}.{name}') as exists;")
            row = cur.fetchone()
            if row and row['exists']:
                # Get size
                cur.execute(f"SELECT pg_size_pretty(pg_total_relation_size('{schema}.{name}')) as sz;")
                sz = cur.fetchone()['sz']
                print(f"  Dropping {kind} {schema}.{name} (size: {sz})...")
                cur.execute(f"DROP {kind} IF EXISTS {schema}.{name} CASCADE;")
                print(f"  -> Dropped {schema}.{name}")
            else:
                print(f"  {kind} {schema}.{name} does not exist (already removed).")
        conn.commit()
    conn.close()
    print("CPI Database cleanup complete.\n")

def cleanup_metabase_metadata():
    print("=" * 70)
    print("2. CLEANING UP UNUSED / ORPHANED TABLES IN METABASE METADATA")
    print("=" * 70)
    
    # Tables to purge from Metabase metadata:
    # 1. Dropped CPI tables
    # 2. Ghost inactive tables from old iterations
    tables_to_purge = [
        # Newly dropped tables
        ("silver", "canonical_items_backup_20260911"),
        ("silver", "nis_official_cpi"),
        ("silver", "coicop_keywords"),
        ("silver", "canonical_items_safe"),
        ("gold", "product_classification"),
        ("staging", "macro_indicators"),
        # Ghost inactive tables
        ("bronze", "raw_prices_unpartitioned_backup"),
        ("gold", "coicop_weights"),
        ("gold", "fct_cpi_forecast"),
        ("gold", "price_anomalies"),
        ("gold", "v_cpi_forecast_chart"),
        ("gold", "vw_aeon_product_divisions"),
        ("ops", "classification_queue"),
        ("ops", "coicop_category_map"),
        ("ops", "coicop_override_manual"),
        ("ops", "dim_coicop_ai_cache"),
        ("silver", "cambodia_cpi_coicop_weights_breakdown"),
        ("silver", "clean_store_prices_unpartitioned_backup"),
        ("staging", "int_coicop_classified"),
        ("staging", "int_prices_cleaned"),
        ("staging", "stg_fx_rates"),
        ("staging", "stg_raw_scrapes")
    ]
    
    conn = get_mb_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Find table IDs in metabase_table
        table_ids = []
        for schema, name in tables_to_purge:
            cur.execute("""
                SELECT id, schema, name, active, visibility_type
                FROM metabase_table
                WHERE db_id = 2 AND schema = %s AND name = %s;
            """, (schema, name))
            rows = cur.fetchall()
            for r in rows:
                table_ids.append((r['id'], r['schema'], r['name']))
        
        print(f"Found {len(table_ids)} table entries to purge from Metabase metadata:")
        for tid, s, n in table_ids:
            print(f"  - Table ID {tid}: {s}.{n}")
        
        if table_ids:
            ids = [t[0] for t in table_ids]
            
            # Clean up foreign key references
            cur.execute("DELETE FROM report_card WHERE table_id = ANY(%s);", (ids,))
            cur.execute("DELETE FROM metric WHERE table_id = ANY(%s);", (ids,))
            cur.execute("DELETE FROM segment WHERE table_id = ANY(%s);", (ids,))
            cur.execute("DELETE FROM sandboxes WHERE table_id = ANY(%s);", (ids,))
            cur.execute("DELETE FROM table_privileges WHERE table_id = ANY(%s);", (ids,))
            
            # Clean up field values and dimensions
            cur.execute("""
                DELETE FROM metabase_fieldvalues 
                WHERE field_id IN (SELECT id FROM metabase_field WHERE table_id = ANY(%s));
            """, (ids,))
            cur.execute("""
                DELETE FROM metric_important_field 
                WHERE field_id IN (SELECT id FROM metabase_field WHERE table_id = ANY(%s));
            """, (ids,))
            cur.execute("""
                DELETE FROM dimension 
                WHERE field_id IN (SELECT id FROM metabase_field WHERE table_id = ANY(%s));
            """, (ids,))
            cur.execute("""
                DELETE FROM dimension 
                WHERE human_readable_field_id IN (SELECT id FROM metabase_field WHERE table_id = ANY(%s));
            """, (ids,))
            
            # Delete fields and tables
            cur.execute("DELETE FROM metabase_field WHERE table_id = ANY(%s);", (ids,))
            cur.execute("DELETE FROM metabase_table WHERE id = ANY(%s);", (ids,))
            conn.commit()
            print(f"Successfully purged {len(ids)} tables and their fields from Metabase.")
        else:
            print("No matching tables found in Metabase.")
            
    conn.close()
    print("Metabase cleanup complete.\n")

if __name__ == "__main__":
    cleanup_cpi_database()
    cleanup_metabase_metadata()
