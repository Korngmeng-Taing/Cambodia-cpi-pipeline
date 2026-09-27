"""
pipeline/product_replacer.py
────────────────────────────
Product Replacement and Quality Adjustment Engine.
Detects when disappearing items can be linked to incoming successor items,
estimates quantity or hedonic quality adjustments, and maintains a complete
audit trail in silver.dim_product_replacements.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

import psycopg2
from psycopg2.extras import execute_batch
from rapidfuzz import fuzz

from pipeline.config import get_db_connection

log = logging.getLogger(__name__)


class ProductReplacer:
    """Detects successor items for discontinued products and logs replacement adjustments."""

    def __init__(self, name_similarity_threshold: float = 0.80):
        self.name_similarity_threshold = name_similarity_threshold

    def find_and_record_replacements(
        self,
        calc_date: date,
        missing_items: list[dict[str, Any]],
        new_items: list[dict[str, Any]],
        conn=None,
    ) -> list[dict[str, Any]]:
        """
        Scans missing items against new candidate items in the same store and COICOP category.
        Records identified links into silver.dim_product_replacements.
        """
        if not missing_items or not new_items:
            return []

        replacements_to_insert = []
        close_conn = False
        if conn is None:
            conn = get_db_connection()
            close_conn = True

        try:
            # Group candidate new items by (store_slug, coicop_code)
            new_item_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for item in new_items:
                key = (str(item.get("store_slug", "")), str(item.get("coicop_code", "")))
                new_item_map.setdefault(key, []).append(item)

            for old_item in missing_items:
                store = str(old_item.get("store_slug", ""))
                coicop = str(old_item.get("coicop_code", ""))
                old_name = str(old_item.get("name_clean", "")).strip().lower()
                candidates = new_item_map.get((store, coicop), [])

                best_match = None
                best_score = 0.0

                for candidate in candidates:
                    new_name = str(candidate.get("name_clean", "")).strip().lower()
                    score = fuzz.token_sort_ratio(old_name, new_name) / 100.0
                    if score > best_score and score >= self.name_similarity_threshold:
                        best_score = score
                        best_match = candidate

                if best_match is not None:
                    # Determine adjustment type
                    old_size = float(old_item.get("package_size_normalized", 0) or 0)
                    new_size = float(best_match.get("package_size_normalized", 0) or 0)

                    replacement_type = "DIRECT_EQUIVALENT"
                    adjustment_factor = 1.0
                    spec_diffs = {}

                    if old_size > 0 and new_size > 0 and abs(old_size - new_size) / old_size > 0.05:
                        replacement_type = "QUANTITY_ADJUSTED"
                        adjustment_factor = round(new_size / old_size, 6)
                        spec_diffs = {"old_size": old_size, "new_size": new_size}
                    elif coicop.startswith("09"):  # Electronics hedonic candidate
                        replacement_type = "HEDONIC_ADJUSTED"
                        adjustment_factor = 1.0  # Base line placeholder unless hedonic regression updates
                        spec_diffs = {"division": "09", "note": "Hedonic spec candidate"}

                    record = {
                        "old_item_id": str(old_item.get("item_id")),
                        "new_item_id": str(best_match.get("item_id")),
                        "replacement_date": calc_date,
                        "coicop_code": coicop,
                        "store_slug": store,
                        "replacement_type": replacement_type,
                        "quality_adjustment_factor": adjustment_factor,
                        "spec_differences": json.dumps(spec_diffs),
                        "confidence_score": round(best_score, 4),
                    }
                    replacements_to_insert.append(record)

            if replacements_to_insert:
                with conn.cursor() as cur:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO silver.dim_product_replacements (
                            old_item_id, new_item_id, replacement_date,
                            coicop_code, store_slug, replacement_type,
                            quality_adjustment_factor, spec_differences,
                            confidence_score
                        ) VALUES (
                            %(old_item_id)s, %(new_item_id)s, %(replacement_date)s,
                            %(coicop_code)s, %(store_slug)s, %(replacement_type)s,
                            %(quality_adjustment_factor)s, %(spec_differences)s,
                            %(confidence_score)s
                        ) ON CONFLICT DO NOTHING;
                        """,
                        replacements_to_insert,
                    )
                conn.commit()
                log.info(
                    "Recorded %d product replacements in silver.dim_product_replacements.",
                    len(replacements_to_insert),
                )

        finally:
            if close_conn:
                conn.close()

        return replacements_to_insert
