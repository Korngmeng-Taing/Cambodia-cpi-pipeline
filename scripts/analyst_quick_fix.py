"""
scripts/analyst_quick_fix.py
────────────────────────────────────
Analyst Interface for manual COICOP correction.
Processes the 'needs review' queue, allowing an analyst to rapidly assign codes
and update the canonical item records.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from pipeline.config import get_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("analyst_quick_fix")

def process_queue():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Fetch items requiring human review
        cur.execute("""
            SELECT item_id, canonical_name, coicop_division, coicop_code
            FROM silver.canonical_items
            WHERE coicop_method = 'human_review_required'
            LIMIT 50;
        """)
        queue = cur.fetchall()

        if not queue:
            log.info("Review queue is empty! All items classified.")
            return

        log.info("Found %d items requiring review.", len(queue))
        log.info("-" * 50)

        for row in queue:
            item_id, name, div, code = row
            print(f"\nItem: {name}")
            print(f"ID: {item_id}")
            print(f"Current: {div} / {code}")

            user_input = input("Enter new [division, code] (e.g. '01, 01.1.1') or 's' to skip, 'q' to quit: ").strip()

            if user_input.lower() == 'q':
                break
            if user_input.lower() == 's':
                continue

            try:
                new_div, new_code = [x.strip() for x in user_input.split(',')]
                # Update canonical item
                cur.execute("""
                    UPDATE silver.canonical_items
                    SET coicop_division = %s,
                        coicop_code = %s,
                        coicop_method = 'manual_override',
                        coicop_confidence = 1.0,
                        coicop_classified_at = NOW()
                    WHERE item_id = %s::uuid;
                """, (new_div, new_code, item_id))

                # Record in manual corrections for rule learning later
                cur.execute("""
                    INSERT INTO silver.manual_item_corrections (item_id, canonical_name, coicop_division, coicop_code, corrected_at)
                    VALUES (%s::uuid, %s, %s, %s, NOW())
                    ON CONFLICT (item_id) DO UPDATE SET
                        coicop_division = EXCLUDED.coicop_division,
                        coicop_code = EXCLUDED.coicop_code,
                        corrected_at = EXCLUDED.corrected_at;
                """, (item_id, name, new_div, new_code))

                conn.commit()
                print("Successfully updated.")

            except (ValueError, IndexError):
                print("Invalid input format. Skipping...")

    except Exception as e:
        log.exception("Queue processing failed: %s", e)
    finally:
        conn.close()

if __name__ == "__main__":
    process_queue()
