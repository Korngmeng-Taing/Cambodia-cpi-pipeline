"""
pipeline/gemini_item_reviewer.py
───────────────────────────────────
AI-Powered Item Match Auto-Reviewer & Deduplication Service (Method 2).

Resolves pending product review rows in `silver.needs_review` using a two-stage hybrid approach:
  Stage 1: High-precision Rule & Attribute Guard (instantly detects conflicting hardware specs / piece counts
           or exact formatting matches without burning API quota).
  Stage 2: Gemini AI Batch Resolver (uses Google Gemini Flash to evaluate semantic equivalence on borderline pairs).

Resolution actions:
  - APPROVE_MATCH: Links the raw observation to the candidate canonical item in `silver.item_match_log`.
  - SPLIT_NEW: Registers a distinct new canonical item in `silver.canonical_items` and links the raw observation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import execute_batch, register_uuid

from pipeline.config import get_database_url
from pipeline.text_clean import clean_name_for_matching

log = logging.getLogger(__name__)

# Model and batch defaults
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
BATCH_SIZE = int(os.getenv("GEMINI_REVIEW_BATCH_SIZE", "40"))
RATE_LIMIT_DELAY = float(os.getenv("GEMINI_BATCH_DELAY_SECONDS", "1.5"))

# Regex patterns for hardware specs, capacities, and measurements
_RE_STORAGE = re.compile(r"\b(\d+)\s*(?:GB|TB|MB)\b", re.IGNORECASE)
_RE_WATTAGE = re.compile(r"\b(\d+)\s*W\b", re.IGNORECASE)
_RE_MAH = re.compile(r"\b(\d+)\s*MAH\b", re.IGNORECASE)
_RE_PCS = re.compile(r"\b(\d+)\s*(?:PCS|PACK|PK|SET)\b", re.IGNORECASE)
_RE_PHONE_SERIES = re.compile(r"\b(?:IPHONE|GALAXY|FOLD|MAGIC|REDMI|XIAOMI|OPPO|VIVO|PIXEL)\s*(\d+[A-Z]*)\b", re.IGNORECASE)

SYSTEM_PROMPT = """You are an expert product deduplication classifier for a Consumer Price Index (CPI) pipeline in Cambodia.
Your job is to compare a "raw_scraped_name" against a "candidate_canonical_name" and decide whether they represent the EXACT SAME product or DIFFERENT product variants.

Decision Rules:
1. "APPROVE_MATCH": The two names refer to the exact same product. Differences are only due to brand prefix, wording order, language translation (Khmer vs English), minor spelling, promo noise, or formatting.
2. "SPLIT_NEW": The two names refer to DIFFERENT products or variants. E.g. different model numbers, different storage capacity (128GB vs 256GB), different wattage/power, different pack size, different route departures/cities, or different product types.

Return a JSON array of objects with the exact schema:
[
  {
    "pair_id": <int>,
    "decision": "APPROVE_MATCH" | "SPLIT_NEW",
    "confidence": <float between 0.0 and 1.0>,
    "reason": "<short explanation under 15 words>"
  }
]
"""


def extract_specs(text: str) -> dict[str, set[str]]:
    """Extracts critical hardware specs and counts from product title."""
    if not text:
        return {}
    t_up = text.upper()
    specs = {
        "storage": {m.group(0).replace(" ", "") for m in _RE_STORAGE.finditer(t_up)},
        "wattage": {m.group(0).replace(" ", "") for m in _RE_WATTAGE.finditer(t_up)},
        "mah": {m.group(0).replace(" ", "") for m in _RE_MAH.finditer(t_up)},
        "pcs": {m.group(0).replace(" ", "") for m in _RE_PCS.finditer(t_up)},
        "series": {m.group(1).upper() for m in _RE_PHONE_SERIES.finditer(t_up)},
    }
    return {k: v for k, v in specs.items() if v}


def evaluate_rule_guard(raw_name: str, candidate_name: str) -> tuple[str, float, str] | None:
    """Fast deterministic rule guard for clear variant splits or exact matches."""
    c_raw = clean_name_for_matching(raw_name)
    c_cand = clean_name_for_matching(candidate_name)

    if c_raw == c_cand:
        return "APPROVE_MATCH", 1.0, "Exact cleaned name match"

    raw_specs = extract_specs(raw_name)
    cand_specs = extract_specs(candidate_name)

    # Check for hard spec conflicts
    for spec_type in ("storage", "wattage", "mah", "pcs", "series"):
        r_vals = raw_specs.get(spec_type, set())
        c_vals = cand_specs.get(spec_type, set())
        if r_vals and c_vals and not (r_vals & c_vals):
            return "SPLIT_NEW", 1.0, f"Conflicting {spec_type}: {r_vals} vs {c_vals}"

    return None


class GeminiItemReviewer:
    """Batch AI & Rule-based auto-reviewer for silver.needs_review queue."""

    def __init__(self, db_conn_str: str | None = None, model_name: str | None = None):
        register_uuid()
        self.db_conn_str = db_conn_str or get_database_url()
        self.model_name = model_name or DEFAULT_MODEL
        self._init_gemini()

    def _init_gemini(self):
        self.model = None
        api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=SYSTEM_PROMPT,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.1},
                )
                log.info("Gemini AI Reviewer initialized with model: %s", self.model_name)
            except Exception as e:
                log.warning("Could not initialize google.generativeai: %s", e)

    def _get_connection(self):
        conn_str = self.db_conn_str.replace("postgresql+psycopg2://", "postgresql://")
        try:
            conn = psycopg2.connect(conn_str)
        except psycopg2.OperationalError:
            if "postgres" in conn_str:
                alt = conn_str.replace("postgres:5432", "localhost:5432")
            else:
                alt = conn_str.replace("localhost:5432", "postgres:5432")
            conn = psycopg2.connect(alt)
        register_uuid(conn_or_curs=conn)
        return conn

    def fetch_pending_reviews(self, conn, limit: int = 5000) -> list[dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    nr.review_id,
                    nr.raw_price_id,
                    nr.item_description_raw,
                    nr.best_match_item_id,
                    nr.best_match_name,
                    nr.confidence,
                    rp.store_id,
                    rp.price,
                    rp.currency,
                    rp.raw_payload ->> 'brand' as brand,
                    rp.raw_payload ->> 'barcode' as barcode,
                    rp.raw_payload ->> 'package_size' as size_norm
                FROM silver.needs_review nr
                JOIN bronze.raw_prices rp ON rp.raw_price_id = nr.raw_price_id
                WHERE nr.status = 'pending'
                ORDER BY nr.confidence DESC, nr.review_id ASC
                LIMIT %s;
            """, (limit,))
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def resolve_with_gemini(self, pairs: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        """Calls Gemini Flash in batch JSON mode to resolve ambiguous pairs."""
        if not self.model or not pairs:
            return {}

        prompt_data = [
            {
                "pair_id": p["pair_id"],
                "raw_scraped_name": p["raw_name"],
                "candidate_canonical_name": p["candidate_name"],
                "store": p.get("store", ""),
            }
            for p in pairs
        ]

        prompt_str = "Evaluate the following product pairs:\n" + json.dumps(prompt_data, ensure_ascii=False, indent=2)
        results = {}

        for attempt in range(3):
            try:
                response = self.model.generate_content(prompt_str)
                resp_text = response.text.strip()
                parsed = json.loads(resp_text)
                if isinstance(parsed, list):
                    for item in parsed:
                        pid = item.get("pair_id")
                        if pid is not None:
                            results[pid] = {
                                "decision": item.get("decision", "SPLIT_NEW"),
                                "confidence": float(item.get("confidence", 0.9)),
                                "reason": item.get("reason", "AI batch decision"),
                                "method": "gemini_ai",
                            }
                break
            except Exception as e:
                log.warning("Gemini batch error (attempt %d/3): %s", attempt + 1, e)
                time.sleep(RATE_LIMIT_DELAY * (attempt + 2))

        return results

    def process_all_pending(self, limit: int = 5000, dry_run: bool = False, use_rules_only: bool = False) -> dict[str, int]:
        conn = self._get_connection()
        stats = {
            "total_pending": 0,
            "rule_approved": 0,
            "rule_split": 0,
            "ai_approved": 0,
            "ai_split": 0,
            "skipped": 0,
        }

        try:
            pending_rows = self.fetch_pending_reviews(conn, limit=limit)
            stats["total_pending"] = len(pending_rows)
            if not pending_rows:
                log.info("No pending reviews found in silver.needs_review.")
                return stats

            log.info("Processing %d pending reviews from silver.needs_review...", len(pending_rows))

            # Group unique (raw_desc, candidate_name) pairs
            unique_pairs: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for row in pending_rows:
                key = (row["item_description_raw"].strip(), row["best_match_name"].strip() if row["best_match_name"] else "")
                unique_pairs.setdefault(key, []).append(row)

            log.info("Found %d distinct product title comparison pairs.", len(unique_pairs))

            # Step 1: Rule & Spec Guard evaluation
            unresolved_pairs: list[dict[str, Any]] = []
            pair_decisions: dict[int, dict[str, Any]] = {}
            pair_id_counter = 1

            for (raw_name, cand_name), rows in unique_pairs.items():
                rule_res = evaluate_rule_guard(raw_name, cand_name)
                if rule_res:
                    decision, conf, reason = rule_res
                    pair_decisions[pair_id_counter] = {
                        "decision": decision,
                        "confidence": conf,
                        "reason": reason,
                        "method": "rule_guard",
                        "rows": rows,
                    }
                else:
                    unresolved_pairs.append({
                        "pair_id": pair_id_counter,
                        "raw_name": raw_name,
                        "candidate_name": cand_name,
                        "store": rows[0]["store_id"],
                        "rows": rows,
                    })
                pair_id_counter += 1

            # Step 2: Resolve ambiguous pairs with Gemini AI or Rule Heuristics
            if unresolved_pairs and self.model and not use_rules_only:
                log.info("Sending %d ambiguous pairs to Gemini in chunks of %d (%d API requests)...", len(unresolved_pairs), BATCH_SIZE, (len(unresolved_pairs) + BATCH_SIZE - 1) // BATCH_SIZE)
                for i in range(0, len(unresolved_pairs), BATCH_SIZE):
                    chunk = unresolved_pairs[i : i + BATCH_SIZE]
                    ai_results = self.resolve_with_gemini(chunk)
                    for item in chunk:
                        pid = item["pair_id"]
                        if pid in ai_results:
                            res = ai_results[pid]
                            pair_decisions[pid] = {
                                "decision": res["decision"],
                                "confidence": res["confidence"],
                                "reason": res["reason"],
                                "method": "gemini_ai",
                                "rows": item["rows"],
                            }
                        else:
                            pair_decisions[pid] = {
                                "decision": "SPLIT_NEW",
                                "confidence": 0.85,
                                "reason": "Ambiguous variant fallback",
                                "method": "fallback_split",
                                "rows": item["rows"],
                            }
                    time.sleep(RATE_LIMIT_DELAY)
            elif unresolved_pairs:
                log.info("Applying rule-based variant split to %d unresolved comparison pairs (0 API requests).", len(unresolved_pairs))
                for item in unresolved_pairs:
                    pair_decisions[item["pair_id"]] = {
                        "decision": "SPLIT_NEW",
                        "confidence": 0.85,
                        "reason": "Unresolved variant auto-split",
                        "method": "heuristic_split",
                        "rows": item["rows"],
                    }

            # Step 3: Apply decisions to Database
            if dry_run:
                for dec_info in pair_decisions.values():
                    dec = dec_info["decision"]
                    method = dec_info["method"]
                    count = len(dec_info["rows"])
                    if dec == "APPROVE_MATCH":
                        if method == "rule_guard":
                            stats["rule_approved"] += count
                        else:
                            stats["ai_approved"] += count
                    else:
                        if method == "rule_guard":
                            stats["rule_split"] += count
                        else:
                            stats["ai_split"] += count
                log.info("[DRY RUN] Would resolve: %s", stats)
                return stats

            self._apply_decisions(conn, pair_decisions, stats)

            conn.commit()
            log.info("Successfully applied auto-review resolutions: %s", stats)
            return stats
        finally:
            conn.close()

    def _apply_decisions(self, conn, pair_decisions: dict[int, dict[str, Any]], stats: dict[str, int]):
        approved_matches: list[tuple[int, uuid.UUID, str, float]] = []
        approved_review_ids: list[int] = []

        new_canonical_items: list[tuple[uuid.UUID, str, str | None, str | None, str | None]] = []
        split_matches: list[tuple[int, uuid.UUID, str, float]] = []
        split_review_ids: list[int] = []

        with conn.cursor() as cur:
            # Collect barcodes only from the current review batch (not the whole table).
            # Loading all canonical_items barcodes into RAM is a memory bomb at scale.
            batch_barcodes = {
                row.get("barcode", "").strip()
                for dec_info in pair_decisions.values()
                for row in dec_info.get("rows", [])
                if row.get("barcode")
            }
            existing_barcodes: dict[str, uuid.UUID] = {}
            if batch_barcodes:
                cur.execute(
                    "SELECT barcode, item_id FROM silver.canonical_items WHERE barcode = ANY(%s);",
                    (list(batch_barcodes),),
                )
                existing_barcodes = {b.strip(): iid for b, iid in cur.fetchall() if b}

        seen_new_barcodes: set[str] = set()

        for dec_info in pair_decisions.values():
            decision = dec_info["decision"]
            method = dec_info["method"]
            conf = dec_info["confidence"]
            rows = dec_info["rows"]

            if decision == "APPROVE_MATCH":
                for r in rows:
                    approved_matches.append((
                        r["raw_price_id"],
                        r["best_match_item_id"],
                        "fuzzy_text",
                        conf,
                    ))
                    approved_review_ids.append(r["review_id"])
                if method == "rule_guard":
                    stats["rule_approved"] += len(rows)
                else:
                    stats["ai_approved"] += len(rows)

            else:  # SPLIT_NEW
                first_row = rows[0]
                barcode = first_row.get("barcode")
                if barcode:
                    barcode = barcode.strip()

                if barcode and barcode in existing_barcodes:
                    matched_item_id = existing_barcodes[barcode]
                    for r in rows:
                        approved_matches.append((
                            r["raw_price_id"],
                            matched_item_id,
                            "barcode_exact",
                            1.0,
                        ))
                        approved_review_ids.append(r["review_id"])
                    stats["rule_approved"] += len(rows)
                    continue

                clean_barcode = barcode if (barcode and barcode not in seen_new_barcodes) else None
                if clean_barcode:
                    seen_new_barcodes.add(clean_barcode)

                # Create one unique canonical item per unique raw title
                new_item_id = uuid.uuid4()
                clean_title = clean_name_for_matching(first_row["item_description_raw"])
                new_canonical_items.append((
                    new_item_id,
                    clean_title,
                    first_row.get("brand"),
                    clean_barcode,
                    first_row.get("size_norm"),
                ))
                for r in rows:
                    split_matches.append((
                        r["raw_price_id"],
                        new_item_id,
                        "new_item",
                        conf,
                    ))
                    split_review_ids.append(r["review_id"])
                if method == "rule_guard":
                    stats["rule_split"] += len(rows)
                else:
                    stats["ai_split"] += len(rows)

        with conn.cursor() as cur:
            # 1. Insert new canonical items
            if new_canonical_items:
                execute_batch(
                    cur,
                    """
                    INSERT INTO silver.canonical_items (item_id, canonical_name, brand, barcode, size_norm)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO NOTHING;
                    """,
                    new_canonical_items,
                    page_size=500,
                )

            # 2. Upsert into item_match_log
            all_matches = approved_matches + split_matches
            if all_matches:
                execute_batch(
                    cur,
                    """
                    INSERT INTO silver.item_match_log (raw_price_id, item_id, match_method, confidence)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (raw_price_id) DO UPDATE 
                    SET item_id = EXCLUDED.item_id,
                        match_method = EXCLUDED.match_method,
                        confidence = EXCLUDED.confidence;
                    """,
                    all_matches,
                    page_size=500,
                )

            # 3. Update needs_review status
            if approved_review_ids:
                execute_batch(
                    cur,
                    """
                    UPDATE silver.needs_review
                    SET status = 'approved',
                        reviewed_at = NOW(),
                        reviewed_by = 'gemini_ai'
                    WHERE review_id = %s;
                    """,
                    [(rid,) for rid in approved_review_ids],
                    page_size=500,
                )

            if split_review_ids:
                execute_batch(
                    cur,
                    """
                    UPDATE silver.needs_review
                    SET status = 'rejected',
                        reviewed_at = NOW(),
                        reviewed_by = 'gemini_ai'
                    WHERE review_id = %s;
                    """,
                    [(rid,) for rid in split_review_ids],
                    page_size=500,
                )


def auto_review_pending_items(
    limit: int = 20000, dry_run: bool = False, use_rules_only: bool = False
) -> dict[str, int]:
    """Top-level convenience function to auto-resolve pending reviews in silver.needs_review."""
    reviewer = GeminiItemReviewer()
    return reviewer.process_all_pending(
        limit=limit, dry_run=dry_run, use_rules_only=use_rules_only
    )

