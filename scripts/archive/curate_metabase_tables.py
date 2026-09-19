"""
Curate Metabase Data Browser visibility:
Hides raw monthly partition tables (57 tables), bronze ingestion landing tables,
and internal pipeline cache tables so end users only see curated, analytics-ready
Gold facts, dimensions, and views in Metabase.
"""

import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    conn = psycopg2.connect("postgresql://metabase:metabase@127.0.0.1:5432/metabase")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Hide all partition tables (%_202% and %_default)
        cur.execute("""
            UPDATE metabase_table
            SET visibility_type = 'hidden'
            WHERE db_id = 2 
              AND (name LIKE '%_202%' OR name LIKE '%_default');
        """)
        partitions_hidden = cur.rowcount
        print(f"Set visibility_type = 'hidden' on {partitions_hidden} raw monthly partition tables.")

        # 2. Hide internal bronze, ops, and internal pipeline support tables
        internal_tables = [
            ('bronze', 'raw_prices'),
            ('bronze', 'scrape_errors'),
            ('ops', 'circuit_breaker_events'),
            ('ops', 'cold_storage_catalog'),
            ('silver', 'canonical_item_barcodes'),
            ('silver', 'dim_canonical_products'),
            ('silver', 'gold_standard_items'),
            ('silver', 'classification_ground_truth'),
            ('silver', 'coicop_critical_traps'),
            ('silver', 'store_purity'),
            ('silver', 'manual_item_corrections'),
            ('silver', 'macro_indicators'),
            ('gold', 'cpi_base_dates'),
            ('gold', 'nis_official_cpi'),
            ('gold', 'fct_elementary_indices')  # Parent partitioned table for Jevons engine
        ]
        
        for schema, name in internal_tables:
            cur.execute("""
                UPDATE metabase_table
                SET visibility_type = 'hidden'
                WHERE db_id = 2 AND schema = %s AND name = %s;
            """, (schema, name))
        print(f"Set visibility_type = 'hidden' on {len(internal_tables)} internal backend/pipeline tables.")

        conn.commit()

        # 3. Report remaining visible tables in Metabase
        cur.execute("""
            SELECT schema, name, display_name
            FROM metabase_table
            WHERE db_id = 2 AND active = true AND visibility_type IS NULL
            ORDER BY schema, name;
        """)
        visible = cur.fetchall()
        print(f"\nRemaining VISIBLE tables in Metabase for analysts ({len(visible)}):")
        for v in visible:
            print(f"  * {v['schema']}.{v['name']}")

    conn.close()

if __name__ == "__main__":
    main()
