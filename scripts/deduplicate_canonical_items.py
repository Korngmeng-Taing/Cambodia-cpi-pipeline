"""
scripts/deduplicate_canonical_items.py
──────────────────────────────────────
Deduplicates silver.canonical_items by canonical_name and size_norm,
elects primary items (prioritizing valid barcodes, embeddings, and price counts),
repoints foreign keys in silver.item_match_log, silver.dim_canonical_products,
and silver.needs_review, and safely removes duplicate rows.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure repo root is in sys.path
repo_root = str(Path(__file__).resolve().parent.parent)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import psycopg2
from psycopg2.extras import register_uuid

from pipeline.config import get_database_url, alternate_host_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def get_connection():
    db_url = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    try:
        conn = psycopg2.connect(db_url)
    except psycopg2.OperationalError:
        conn = psycopg2.connect(alternate_host_url(db_url))
    register_uuid(conn_or_curs=conn)
    return conn


def run_deduplication(dry_run: bool = False):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1. Create backup table if not exists
            if not dry_run:
                log.info("Creating backup snapshot silver.canonical_items_backup_20260911...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS silver.canonical_items_backup_20260911 AS
                    SELECT * FROM silver.canonical_items;
                """)
                conn.commit()

            log.info("Analyzing duplicate canonical items...")

            # 2. Build merge mapping using Window Functions
            # Elect winner:
            # Rank 1: has valid barcode (1 if not null, 0 if null)
            # Rank 2: has embedding (1 if not null, 0 if null)
            # Rank 3: match log count descending
            # Rank 4: item_id ascending
            cur.execute("""
                CREATE TEMP TABLE temp_canonical_ranked AS
                WITH item_match_counts AS (
                    SELECT item_id, COUNT(*) AS price_count
                    FROM silver.item_match_log
                    GROUP BY item_id
                ),
                ranked_items AS (
                    SELECT 
                        ci.item_id,
                        ci.canonical_name,
                        ci.size_norm,
                        ci.barcode,
                        UPPER(TRIM(REGEXP_REPLACE(ci.canonical_name, '\\s+', ' ', 'g'))) AS norm_name,
                        COALESCE(ci.size_norm, '') AS norm_size,
                        ROW_NUMBER() OVER (
                            PARTITION BY UPPER(TRIM(REGEXP_REPLACE(ci.canonical_name, '\\s+', ' ', 'g'))), COALESCE(ci.size_norm, '')
                            ORDER BY 
                                CASE WHEN ci.barcode IS NOT NULL AND ci.barcode != '' THEN 1 ELSE 2 END,
                                CASE WHEN ci.embedding IS NOT NULL THEN 1 ELSE 2 END,
                                COALESCE(imc.price_count, 0) DESC,
                                ci.item_id ASC
                        ) AS rank_in_group,
                        FIRST_VALUE(ci.item_id) OVER (
                            PARTITION BY UPPER(TRIM(REGEXP_REPLACE(ci.canonical_name, '\\s+', ' ', 'g'))), COALESCE(ci.size_norm, '')
                            ORDER BY 
                                CASE WHEN ci.barcode IS NOT NULL AND ci.barcode != '' THEN 1 ELSE 2 END,
                                CASE WHEN ci.embedding IS NOT NULL THEN 1 ELSE 2 END,
                                COALESCE(imc.price_count, 0) DESC,
                                ci.item_id ASC
                        ) AS primary_item_id
                    FROM silver.canonical_items ci
                    LEFT JOIN item_match_counts imc ON ci.item_id = imc.item_id
                    WHERE ci.canonical_name IS NOT NULL
                )
                SELECT item_id AS duplicate_item_id, primary_item_id
                FROM ranked_items
                WHERE item_id != primary_item_id;
            """)

            cur.execute("SELECT COUNT(*) FROM temp_canonical_ranked;")
            duplicate_count = cur.fetchone()[0]
            log.info("Found %d duplicate canonical items to merge.", duplicate_count)

            if duplicate_count == 0:
                log.info("No duplicates found. Database is already clean!")
                return

            if dry_run:
                log.info("[DRY RUN] Would merge %d duplicate canonical items. Exiting.", duplicate_count)
                return

            # 3. Repoint foreign keys in silver.item_match_log
            log.info("Repointing silver.item_match_log references...")
            cur.execute("""
                UPDATE silver.item_match_log iml
                SET item_id = m.primary_item_id
                FROM temp_canonical_ranked m
                WHERE iml.item_id = m.duplicate_item_id;
            """)
            log.info("Repointed %d rows in silver.item_match_log.", cur.rowcount)

            # 4. Repoint silver.dim_canonical_products
            log.info("Repointing silver.dim_canonical_products...")
            # First remove conflicts if primary already has this (source_name, raw_item_id)
            cur.execute("""
                DELETE FROM silver.dim_canonical_products dcp
                WHERE dcp.canonical_item_id IN (SELECT duplicate_item_id FROM temp_canonical_ranked)
                  AND EXISTS (
                      SELECT 1 FROM silver.dim_canonical_products target
                      JOIN temp_canonical_ranked m ON target.canonical_item_id = m.primary_item_id
                      WHERE target.source_name = dcp.source_name 
                        AND target.raw_item_id = dcp.raw_item_id
                  );
            """)
            cur.execute("""
                UPDATE silver.dim_canonical_products dcp
                SET canonical_item_id = m.primary_item_id
                FROM temp_canonical_ranked m
                WHERE dcp.canonical_item_id = m.duplicate_item_id;
            """)
            log.info("Repointed %d rows in silver.dim_canonical_products.", cur.rowcount)

            # 5. Repoint silver.needs_review
            log.info("Repointing silver.needs_review...")
            cur.execute("""
                UPDATE silver.needs_review nr
                SET best_match_item_id = m.primary_item_id
                FROM temp_canonical_ranked m
                WHERE nr.best_match_item_id = m.duplicate_item_id;
            """)

            # 6. Repoint silver.manual_item_corrections if present
            try:
                cur.execute("""
                    UPDATE silver.manual_item_corrections mic
                    SET item_id = m.primary_item_id
                    FROM temp_canonical_ranked m
                    WHERE mic.item_id = m.duplicate_item_id;
                """)
            except Exception:
                pass

            # 7. Delete duplicates from silver.canonical_items
            log.info("Deleting %d duplicate rows from silver.canonical_items...", duplicate_count)
            cur.execute("""
                DELETE FROM silver.canonical_items
                WHERE item_id IN (SELECT duplicate_item_id FROM temp_canonical_ranked);
            """)
            log.info("Successfully deleted %d duplicate rows from silver.canonical_items.", cur.rowcount)

            conn.commit()

            # 8. Post-verification
            cur.execute("SELECT COUNT(*) FROM silver.canonical_items;")
            new_total = cur.fetchone()[0]
            log.info("Deduplication complete! Total unique canonical items now: %d", new_total)

    except Exception as e:
        conn.rollback()
        log.error("Error during canonical deduplication: %s", e, exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_deduplication(dry_run=dry_run)
