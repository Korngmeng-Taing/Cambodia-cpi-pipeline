"""
scripts/backfill_silver_pipeline.py
───────────────────────────────────
Historical Backfill Utility for the Silver Layer:
Re-runs Vector Item Matching, Spec Guards, and 12-Division COICOP Classification
for past dates (e.g. from 2026-08-18 onwards).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg2
from pipeline.config import get_database_url
from pipeline.item_matcher import ItemMatcher
from pipeline.key_pool import get_key_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("backfill_silver_pipeline")


def get_db_connection():
    from pipeline.config import alternate_host_url
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    try:
        return psycopg2.connect(conn_str)
    except psycopg2.OperationalError:
        return psycopg2.connect(alternate_host_url(conn_str))


def reset_silver_for_date_range(start_date: str, end_date: str, conn, full_reset: bool = False):
    """Safely cleans Silver match records for the backfill window so they re-process with the new pipeline."""
    log.info("Resetting Silver match logs between %s and %s (full_reset=%s)...", start_date, end_date, full_reset)
    with conn.cursor() as cur:
        # 1. Clear item match logs for observations in date range
        cur.execute(
            """
            DELETE FROM silver.item_match_log
            WHERE raw_price_id IN (
                SELECT raw_price_id FROM bronze.raw_prices
                WHERE scraped_at >= %s::date AND scraped_at < (%s::date + INTERVAL '1 day')
            )
            """,
            (start_date, end_date)
        )
        deleted_matches = cur.rowcount

        # 2. Clear review queue for the range
        cur.execute(
            """
            DELETE FROM silver.needs_review
            WHERE raw_price_id IN (
                SELECT raw_price_id FROM bronze.raw_prices
                WHERE scraped_at >= %s::date AND scraped_at < (%s::date + INTERVAL '1 day')
            )
            """,
            (start_date, end_date)
        )
        deleted_reviews = cur.rowcount

        if full_reset:
            cur.execute("DELETE FROM silver.dim_canonical_products;")
            cur.execute("DELETE FROM silver.canonical_items;")
            log.info("Full reset: Emptied silver.canonical_items and silver.dim_canonical_products.")

        conn.commit()

    log.info("Reset complete: Cleared %d match logs and %d review rows.", deleted_matches, deleted_reviews)


def run_backfill(start_date: str, end_date: str | None = None, full_reset: bool = False):
    pool = get_key_pool()
    log.info("Initializing Backfill with %d active Gemini API key(s)...", pool.get_key_count())

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else datetime.now().date()

    conn = None
    try:
        conn = get_db_connection()
        matcher = ItemMatcher()

        # Reset date range in Silver
        reset_silver_for_date_range(start_date, end_dt.strftime("%Y-%m-%d"), conn, full_reset=full_reset)

        # Iterate day by day in chronological order
        curr_dt = start_dt
        total_days = (end_dt - start_dt).days + 1
        day_idx = 1

        grand_totals = {
            "matched_exact": 0,
            "matched_fuzzy": 0,
            "sent_to_review": 0,
            "new_items_created": 0,
        }

        while curr_dt <= end_dt:
            ds = curr_dt.strftime("%Y-%m-%d")
            log.info("==================================================")
            log.info("Processing Day %d/%d: %s", day_idx, total_days, ds)
            log.info("==================================================")

            stats = matcher.process_unmatched_batch(limit=200000, scrape_date=ds)
            log.info("Day %s Stats: %s", ds, stats)

            for k in grand_totals:
                grand_totals[k] += stats.get(k, 0)

            curr_dt += timedelta(days=1)
            day_idx += 1

        log.info("==================================================")
        log.info("BACKFILL COMPLETED SUCCESSFULLY!")
        log.info("Grand Totals: %s", grand_totals)
        log.info("==================================================")

    finally:
        if conn is not None:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill Silver Layer Item Matching & COICOP Classification")
    parser.add_argument("--start-date", type=str, default="2026-08-18", help="Start date (YYYY-MM-DD), default: 2026-08-18")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD), default: today")
    parser.add_argument("--full-reset", action="store_true", help="Wipe silver.canonical_items and re-generate catalog from scratch")
    args = parser.parse_args()

    run_backfill(args.start_date, args.end_date, full_reset=args.full_reset)


if __name__ == "__main__":
    main()
