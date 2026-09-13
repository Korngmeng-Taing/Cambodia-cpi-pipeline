"""
scripts/deduplicate_canonical_items.py
────────────────────────────────────────
Deduplicates silver.canonical_items based on strict physical specification identity:
  (UPPER(TRIM(canonical_name))) where non-null size_norm matches or is null.

Crucial distinction:
  - If identical product name has different distinct sizes (e.g. 200g vs 50g, 400g vs 500g):
    -> PRESERVES as separate canonical items!
  - If duplicate product names have the same size (e.g. 330ml vs 330ml) or NULL size:
    -> MERGES into 1 master canonical item!
    -> Migrates secondary barcodes into silver.canonical_item_barcodes as aliases.
    -> Re-points foreign key references in child tables.
    -> Deletes secondary duplicate rows from silver.canonical_items.
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from pipeline.config import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_canonical_deduplication() -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Harmonize bakery items falsely classified as cleaning sponges
            logger.info("1. Harmonizing false sponge cake / bakery trap classifications...")
            cur.execute("""
                UPDATE silver.canonical_items
                SET 
                    coicop_division = '01',
                    coicop_code = '01.1.1',
                    coicop_method = 'harmonized_bakery_sponge'
                WHERE canonical_name ~* '\\y(sponge cake|sponge roll|sponge pudding|bakewell sponge|toffee sponge)\\y'
                  AND coicop_division = '05';
            """)
            sponge_fixed = cur.rowcount
            logger.info("   -> Fixed %d bakery items back to Division 01 (Bread & Cereals).", sponge_fixed)

            # 2. Harmonize Toothbrush / Toothpaste tumblers to Household Glassware (05.5.1)
            logger.info("2. Harmonizing toothbrush / toothpaste tumblers...")
            cur.execute("""
                UPDATE silver.canonical_items
                SET 
                    coicop_division = '05',
                    coicop_code = '05.5.1',
                    coicop_method = 'harmonized_household_tumbler'
                WHERE canonical_name ~* '\\y(toothpaste & toothbrush tumbler|toothbrush holder)\\y'
                  AND coicop_division = '12';
            """)
            tumbler_fixed = cur.rowcount
            logger.info("   -> Fixed %d tumblers to Division 05 (Household Glassware).", tumbler_fixed)

            # 3. Scan all canonical items with duplicate names
            logger.info("3. Scanning for duplicate canonical items by normalized title...")
            cur.execute("""
                SELECT item_id, canonical_name, barcode, size_norm, created_at
                FROM silver.canonical_items
                ORDER BY created_at ASC;
            """)
            all_rows = cur.fetchall()
            logger.info("   -> Loaded %d total canonical items from database.", len(all_rows))

            # Group items by normalized title: UPPER(TRIM(canonical_name))
            name_groups = defaultdict(list)
            for row in all_rows:
                item_id, name, barcode, size_norm, created_at = row
                if not name:
                    continue
                norm_name = str(name).strip().upper()
                name_groups[norm_name].append({
                    "item_id": item_id,
                    "name": name,
                    "barcode": str(barcode).strip() if barcode else None,
                    "size_norm": str(size_norm).strip().upper() if size_norm else "",
                    "created_at": created_at,
                })

            # Sub-group by size: items with different explicit sizes remain separate!
            merge_batches = []
            for norm_name, items in name_groups.items():
                if len(items) <= 1:
                    continue

                # Partition items into size buckets
                size_buckets = defaultdict(list)
                null_size_items = []
                for it in items:
                    if it["size_norm"]:
                        size_buckets[it["size_norm"]].append(it)
                    else:
                        null_size_items.append(it)

                # If there are explicit size buckets:
                # Merge items within each explicit size bucket
                for sz, bucket_items in size_buckets.items():
                    if len(bucket_items) > 1:
                        merge_batches.append(bucket_items)

                # If only 1 explicit size bucket exists and there are null-size items,
                # the null-size items belong to that same product size
                if len(size_buckets) == 1 and null_size_items:
                    single_sz = list(size_buckets.keys())[0]
                    size_buckets[single_sz].extend(null_size_items)
                    if size_buckets[single_sz] not in merge_batches and len(size_buckets[single_sz]) > 1:
                        merge_batches.append(size_buckets[single_sz])
                elif len(size_buckets) == 0 and len(null_size_items) > 1:
                    # All items have null size -> same product
                    merge_batches.append(null_size_items)

            logger.info("   -> Formed %d merge clusters sharing the same name and specification size.", len(merge_batches))

            if not merge_batches:
                logger.info("No duplicates found to merge. Canonical catalog is already clean.")
                conn.commit()
                return

            total_merged = 0
            barcode_aliases_added = 0

            for cluster in merge_batches:
                # Sort cluster: prioritize item with valid barcode, then earliest created
                cluster.sort(key=lambda x: (
                    0 if (x["barcode"] and len(x["barcode"]) >= 8) else 1,
                    x["created_at"]
                ))
                master_item = cluster[0]
                master_id = master_item["item_id"]
                secondary_items = cluster[1:]
                secondary_ids = [it["item_id"] for it in secondary_items]

                # A. Register all barcodes in cluster into silver.canonical_item_barcodes
                for it in cluster:
                    bc = it["barcode"]
                    if bc:
                        cur.execute("""
                            INSERT INTO silver.canonical_item_barcodes (barcode, item_id, store_slug)
                            VALUES (%s, %s, 'merged_dedup')
                            ON CONFLICT (barcode) DO NOTHING;
                        """, (bc, master_id))
                        barcode_aliases_added += 1

                # B. Re-point silver.item_match_log
                cur.execute("""
                    UPDATE silver.item_match_log
                    SET item_id = %s
                    WHERE item_id = ANY(%s::uuid[]);
                """, (master_id, secondary_ids))

                # C. Re-point silver.clean_store_prices
                cur.execute("""
                    UPDATE silver.clean_store_prices
                    SET item_id = %s::text
                    WHERE item_id = ANY(%s::text[]);
                """, (str(master_id), [str(sid) for sid in secondary_ids]))

                # D. Re-point silver.dim_canonical_products (SKU registry)
                cur.execute("""
                    UPDATE silver.dim_canonical_products
                    SET canonical_item_id = %s
                    WHERE canonical_item_id = ANY(%s::uuid[]);
                """, (master_id, secondary_ids))

                # E. Delete secondary redundant canonical items
                cur.execute("""
                    DELETE FROM silver.canonical_items
                    WHERE item_id = ANY(%s::uuid[]);
                """, (secondary_ids,))

                total_merged += len(secondary_ids)

            conn.commit()
            logger.info("✅ Canonical deduplication complete!")
            logger.info("   -> Merged and eliminated %d redundant duplicate rows.", total_merged)
            logger.info("   -> Preserved %d barcode aliases in silver.canonical_item_barcodes.", barcode_aliases_added)

            # Final verification
            cur.execute("SELECT COUNT(*) FROM silver.canonical_items;")
            new_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT coicop_division) FROM silver.canonical_items;")
            div_count = cur.fetchone()[0]
            logger.info("📊 New canonical_items row count: %d (Unique divisions: %d)", new_count, div_count)

    finally:
        conn.close()


if __name__ == "__main__":
    run_canonical_deduplication()
