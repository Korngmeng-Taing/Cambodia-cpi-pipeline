"""
scripts/fix_partition_names.py
───────────────────────────────
Fixes the partition naming mismatch in PostgreSQL:
1. Renames bronze.raw_prices_part_YYYY_MM to bronze.raw_prices_YYYY_MM
2. Renames silver.clean_store_prices_part_YYYY_MM to silver.clean_store_prices_YYYY_MM
3. Renames *_part_default to *_default
4. Updates ops.ensure_monthly_partition stored procedure to check partition bounds / existing partitions safely.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import get_db_connection

def fix_partition_names():
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Step 1: Find partitions that need renaming
        cur.execute("""
            SELECT n.nspname, parent.relname as parent_name, child.relname as old_name
            FROM pg_inherits i
            JOIN pg_class parent ON i.inhparent = parent.oid
            JOIN pg_class child ON i.inhrelid = child.oid
            JOIN pg_namespace n ON n.oid = parent.relnamespace
            WHERE n.nspname IN ('bronze', 'silver')
              AND parent.relkind = 'p'
              AND (child.relname LIKE '%_part_%' OR child.relname LIKE '%_part_default')
            ORDER BY n.nspname, child.relname;
        """)
        partitions_to_rename = cur.fetchall()
        print(f"Found {len(partitions_to_rename)} partitions to rename:")

        for nspname, _parent_name, old_name in partitions_to_rename:
            if "_part_default" in old_name:
                new_name = old_name.replace("_part_default", "_default")
            else:
                new_name = old_name.replace("_part_", "_")
            print(f"  Renaming {nspname}.{old_name} -> {nspname}.{new_name}")
            cur.execute(f'ALTER TABLE "{nspname}"."{old_name}" RENAME TO "{new_name}";')

        # Step 2: Update ops.ensure_monthly_partition function to be robust and idempotent
        print("Updating ops.ensure_monthly_partition function...")
        cur.execute("""
        CREATE OR REPLACE FUNCTION ops.ensure_monthly_partition(
            p_schema_name TEXT,
            p_table_name TEXT,
            p_year INT,
            p_month INT
        ) RETURNS VOID AS $$
        DECLARE
            v_part_name TEXT;
            v_start_date DATE;
            v_end_date DATE;
            v_sql TEXT;
            v_exists BOOLEAN;
        BEGIN
            v_start_date := MAKE_DATE(p_year, p_month, 1);
            v_end_date := (v_start_date + INTERVAL '1 month')::DATE;
            v_part_name := FORMAT('%s_%s_%s', p_table_name, p_year, TO_CHAR(v_start_date, 'MM'));

            -- Check if a partition covering this range already exists for the parent table
            -- (regardless of whether named table_YYYY_MM or table_part_YYYY_MM)
            SELECT EXISTS (
                SELECT 1
                FROM pg_inherits i
                JOIN pg_class parent ON i.inhparent = parent.oid
                JOIN pg_class child ON i.inhrelid = child.oid
                JOIN pg_namespace n ON n.oid = parent.relnamespace
                WHERE n.nspname = p_schema_name
                  AND parent.relname = p_table_name
                  AND (
                      child.relname = v_part_name
                      OR child.relname = FORMAT('%s_part_%s_%s', p_table_name, p_year, TO_CHAR(v_start_date, 'MM'))
                      OR pg_get_expr(child.relpartbound, child.oid) LIKE FORMAT('%%''%s%%', v_start_date)
                  )
            ) INTO v_exists;

            IF NOT v_exists THEN
                v_sql := FORMAT(
                    'CREATE TABLE IF NOT EXISTS %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L);',
                    p_schema_name, v_part_name, p_schema_name, p_table_name,
                    v_start_date, v_end_date
                );
                EXECUTE v_sql;
                RAISE NOTICE 'Created partition %.% from % to %', p_schema_name, v_part_name, v_start_date, v_end_date;
            ELSE
                RAISE NOTICE 'Partition for %.% (% to %) already exists, skipping.', p_schema_name, p_table_name, v_start_date, v_end_date;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """)

        conn.commit()
        print("Successfully committed partition renames and function update!")
    except Exception as e:
        conn.rollback()
        print(f"Error during partition renaming: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    fix_partition_names()
