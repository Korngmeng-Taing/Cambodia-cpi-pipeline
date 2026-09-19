"""
scripts/merge_canonical_items.py
────────────────────────────────────
Canonical Item Deduplication & Merger Tool.
Identifies clusters of near-identical items using semantic vector similarity
and physical spec guards, then merges them into a single authoritative record.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from pipeline.config import get_db_connection
from pipeline.vector_item_matcher import VectorItemMatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("merge_canonical_items")

def load_catalog(conn):
    """Load all items for analysis."""
    cur = conn.cursor()
    cur.execute("""
        SELECT item_id, canonical_name, coicop_code, coicop_division
        FROM silver.canonical_items
        WHERE embedding IS NOT NULL;
    """)
    return cur.fetchall()

def find_merge_candidates(conn, matcher: VectorItemMatcher, catalog):
    """
    For every item in the catalog, find high-similarity neighbors.
    """
    candidates = [] # List of (item_id_1, item_id_2, sim)
    processed_ids = set()

    log.info("Scanning catalog for duplicate clusters (this may take a few minutes)...")
    for row in catalog:
        item_id, name, code, div = row
        if item_id in processed_ids:
            continue

        # Use HNSW index to find top candidates
        match_res = matcher.match_candidate_db(
            candidate_name=name,
            conn=conn,
            sim_auto_threshold=1.0, # We want all high-sim matches, not just one
            sim_review_threshold=0.95, # Merge threshold
        )

        if match_res and match_res["decision"] == "APPROVE_MATCH":
            matched_id = match_res["matched_item_id"]
            if matched_id != str(item_id):
                sim = match_res["confidence"]
                candidates.append((str(item_id), matched_id, sim))
                processed_ids.add(matched_id)

        processed_ids.add(item_id)

    return candidates

def execute_merge(conn, merges: list[tuple[str, str]]):
    """
    Merges item_b into item_a.
    1. Update silver.clean_store_prices observations.
    2. Update gold.dim_items.
    3. Delete the duplicate canonical_item.
    """
    cur = conn.cursor()
    for a_id, b_id in merges:
        log.info("Merging %s -> %s", b_id, a_id)

        # Update observations
        cur.execute("""
            UPDATE silver.clean_store_prices
            SET item_id = %s::uuid
            WHERE item_id = %s::uuid;
        """, (a_id, b_id))

        # Update gold dim_items
        cur.execute("""
            UPDATE gold.dim_items
            SET item_id = %s::text
            WHERE item_id = %s::text;
        """, (a_id, b_id))

        # Delete the duplicate canonical record
        cur.execute("DELETE FROM silver.canonical_items WHERE item_id = %s::uuid;", (b_id,))

def run(execute: bool = False):
    conn = get_db_connection()
    matcher = VectorItemMatcher()

    try:
        catalog = load_catalog(conn)
        log.info("Loaded %d items from catalog.", len(catalog))

        candidates = find_merge_candidates(conn, matcher, catalog)

        if not candidates:
            log.info("No high-similarity duplicates found. Catalog is clean!")
            return

        log.info("=" * 70)
        log.info("MERGE CANDIDATES FOUND (%d pairs):", len(candidates))
        log.info("-" * 70)

        merges_to_apply = []
        for a, b, sim in candidates:
            log.info("SIM %.4f | %s <-> %s", sim, a, b)
            # In a real tool, we'd prompt the user. Here we auto-suggest based on sim > 0.98
            if sim > 0.98:
                merges_to_apply.append((a, b))

        log.info("=" * 70)
        log.info("Suggested merges (Sim > 0.98): %d", len(merges_to_apply))

        if execute:
            if not merges_to_apply:
                log.info("No high-confidence merges to execute.")
                return

            log.info("APPLYING MERGES...")
            execute_merge(conn, merges_to_apply)
            conn.commit()
            log.info("Merges committed successfully!")
        else:
            log.info("DRY RUN mode: No changes applied. Use --execute to merge.")

    except Exception as e:
        conn.rollback()
        log.exception("Merge process failed: %s", e)
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Canonical Item Deduplication Tool")
    parser.add_argument("--execute", action="store_true", help="Apply the merges to the database")
    args = parser.parse_args()

    run(execute=args.execute)
