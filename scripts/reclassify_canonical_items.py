"""
scripts/reclassify_canonical_items.py
─────────────────────────────────────
Authoritative, high-throughput reclassification engine for silver.canonical_items,
silver.clean_store_prices, and gold.dim_items.

This engine has been upgraded to use the HybridCOICOPClassifier,
leveraging a hierarchical Local-First AI flow (Purity -> Semantic -> Ollama -> Gemini).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import execute_batch

from pipeline.config import get_db_connection
from pipeline.hybrid_embeddings_classifier import HybridCOICOPClassifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("reclassify_canonical_items")

# Stores that are multi-category retail grocers / hypermarkets / general e-commerce
SUPERMARKET_STORES = {
    "aeon", "aeon3", "delishop", "grab_lucky", "grab_chipmong", "l192"
}

def run(dry_run: bool = True, batch_size: int = 2000):
    log.info("Connecting to CPI PostgreSQL database...")
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Initialize the high-precision classifier
        log.info("Initializing Hybrid COICOP Classifier (loading embeddings)...")
        classifier = HybridCOICOPClassifier()

        log.info("Loading all canonical items...")
        cur.execute("""
            SELECT
                ci.item_id::text,
                ci.canonical_name,
                ci.coicop_division,
                ci.coicop_code,
                array_agg(distinct s.store_slug) filter (where s.store_slug is not null) as stores,
                array_agg(distinct s.category_native) filter (where s.category_native is not null and s.category_native <> '') as categories
            FROM silver.canonical_items ci
            LEFT JOIN silver.clean_store_prices s ON ci.item_id::text = s.item_id::text
            GROUP BY ci.item_id, ci.canonical_name, ci.coicop_division, ci.coicop_code;
        """)
        rows = cur.fetchall()
        total_items = len(rows)
        log.info("Loaded %d canonical items from database.", total_items)

        reclassified_rows = []
        div_counts = {}
        code_counts = {}
        changes_count = 0
        div_changes_count = 0

        def process_item(row):
            item_id, name, cur_div, cur_code, stores, categories = row
            stores_list = stores or []
            cat_list = categories or []
            ref_store = stores_list[0] if stores_list else "unknown"

            # Perform high-precision AI classification
            res = classifier.classify_product(
                product_name=name or "",
                store_slug=ref_store,
                category_native=" ".join(cat_list)
            )

            new_div = res["division"]
            new_code = res["code"]
            method = res["method"]
            conf = res["confidence"]

            # Apply Supermarket Disqualification Logic (post-AI filter)
            if stores_list and set(stores_list).issubset(SUPERMARKET_STORES):
                if new_div in ("04", "11"):
                    new_div = "01"
                    new_code = "01.1.9"
                    method = f"disqualified_{new_div}_to_groceries"

            return (new_div, new_code, method, conf, item_id, cur_div, cur_code)

        log.info("Processing items in parallel (ThreadPoolExecutor)...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_item, row) for row in rows]
            for i, future in enumerate(as_completed(futures)):
                new_div, new_code, method, conf, item_id, cur_div, cur_code = future.result()

                div_counts[new_div] = div_counts.get(new_div, 0) + 1
                code_counts[new_code] = code_counts.get(new_code, 0) + 1

                if new_code != cur_code:
                    changes_count += 1
                if new_div != cur_div:
                    div_changes_count += 1

                reclassified_rows.append((new_div, new_code, method, conf, item_id))

                if (i + 1) % 100 == 0:
                    log.info("Processed %d/%d items...", i + 1, total_items)

        log.info("=" * 70)
        log.info("RECLASSIFICATION SUMMARY (Total: %d items):", total_items)
        log.info("  Items with 5-digit code changes: %d (%.2f%%)", changes_count, changes_count * 100.0 / total_items)
        log.info("  Items with 2-digit division changes: %d (%.2f%%)", div_changes_count, div_changes_count * 100.0 / total_items)
        log.info("-" * 70)
        log.info("NEW DIVISION DISTRIBUTION:")
        for div in sorted(div_counts.keys()):
            cnt = div_counts[div]
            log.info("  Division %s: %5d items (%.2f%%)", div, cnt, cnt * 100.0 / total_items)
        log.info("-" * 70)
        log.info("TOP 15 5-DIGIT CODES:")
        for code, cnt in sorted(code_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
            log.info("  Code %s: %5d items (%.2f%%)", code, cnt, cnt * 100.0 / total_items)
        log.info("=" * 70)

        if dry_run:
            log.info("DRY RUN mode active — no database changes committed.")
            return

        log.info("APPLYING DATABASE UPDATES...")

        execute_batch(cur, """
            UPDATE silver.canonical_items
            SET coicop_division = %s,
                coicop_code = %s,
                coicop_method = %s,
                coicop_confidence = %s,
                coicop_classified_at = NOW()
            WHERE item_id = %s::uuid;
        """, reclassified_rows, page_size=batch_size)

        cur.execute("""
            UPDATE gold.dim_items di
            SET coicop_division = ci.coicop_division,
                coicop_code = ci.coicop_code
            FROM silver.canonical_items ci
            WHERE di.item_id = ci.item_id::text
              AND (di.coicop_code != ci.coicop_code OR di.coicop_division != ci.coicop_division);
        """)

        cur.execute("""
            UPDATE silver.clean_store_prices s
            SET coicop_division = ci.coicop_division,
                coicop_code = ci.coicop_code,
                coicop_method = 'canonical_sync',
                coicop_confidence = ci.coicop_confidence
            FROM silver.canonical_items ci
            WHERE s.item_id::text = ci.item_id::text
              AND (s.coicop_code != ci.coicop_code OR s.coicop_division != ci.coicop_division);
        """)

        conn.commit()
        log.info("ALL DATABASE UPDATES COMMITTED SUCCESSFULLY!")

    except Exception as e:
        conn.rollback()
        log.exception("Reclassification failed! Rolled back transaction: %s", e)
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reclassify silver.canonical_items using Hybrid AI.")
    parser.add_argument("--execute", action="store_true", help="Execute database updates (default is dry-run)")
    parser.add_argument("--batch-size", type=int, default=2000, help="Batch size for execute_batch")
    args = parser.parse_args()

    run(dry_run=not args.execute, batch_size=args.batch_size)
