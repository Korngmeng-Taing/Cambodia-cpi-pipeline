"""
pipeline/gemini_coicop_classifier.py
───────────────────────────────────
Direct Gemini Flash AI COICOP Classification Service.
Replaces legacy 4-tier tree/Ollama/regex trap with a high-accuracy, 
one-shot batch classification engine using Google Gemini.

Key capabilities:
- Native bilingual comprehension (Khmer & English).
- Domain guardrails (Pet food, personal care, supermarket meals, alcohol).
- Batch processing (30-50 products per call).
- Automatic rotation across Gemini API keys via GeminiKeyPool.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import uuid

import psycopg2
from psycopg2.extras import execute_batch, register_uuid

from pipeline.config import get_database_url
from pipeline.key_pool import GeminiKeyPool

try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GENAI = True
except ImportError:
    genai = None
    genai_types = None
    HAS_GENAI = False

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
BATCH_SIZE = int(os.getenv("COICOP_BATCH_SIZE", "40"))
MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "5"))

SYSTEM_PROMPT = """You are an expert UN COICOP (Classification of Individual Consumption According to Purpose) classification engine for the Consumer Price Index (CPI) in Cambodia.
Your job is to classify consumer products strictly according to the official Cambodia National Institute of Statistics (NIS) 4-digit COICOP Class taxonomy (formatted with dots: DD.G.C, e.g. 01.1.1, 01.2.2, 07.2.2, 12.1.3).

Input will be a list of products with their ID, name, brand (optional), and store context.
For each product, determine:
1. "coicop_division": 2-digit string from '01' to '12':
   01: Food and non-alcoholic beverages
   02: Alcoholic beverages, tobacco and narcotics
   03: Clothing and footwear
   04: Housing, water, electricity, gas and other fuels
   05: Furnishings, household equipment and routine household maintenance
   06: Health
   07: Transport
   08: Communication
   09: Recreation and culture
   10: Education
   11: Restaurants and hotels
   12: Miscellaneous goods and services

2. "coicop_code": EXACT 4-digit NIS Cambodia COICOP Class code (format DD.G.C, e.g. "01.1.1", "01.1.2", "01.2.2", "02.1.3", "03.1.2", "05.6.1", "06.1.1", "07.2.2", "08.3.0", "09.3.1", "11.1.1", "12.1.3").
   NEVER return 5 digits (e.g. do NOT return 01.1.1.1, use 01.1.1).
   NEVER return only 2 digits. ALWAYS return the exact 4-digit class code (DD.G.C).

3. "confidence": Float between 0.0 and 1.0.

CRITICAL GUARDRAIL RULES:
- PET FOOD & ACCESSORIES: Dog food, cat food, pet treats, cat litter -> MUST BE "09.3.1" (Games, toys and hobbies / pets), NEVER Division 01 (Human food).
- PERSONAL CARE & HYGIENE: Shampoo, soaps, skincare, sunscreen, toothpaste, diapers, sanitary pads -> MUST BE "12.1.3" or "12.1.1" (Personal Care), NEVER Division 01 or 05.
- SUPERMARKET PACKAGED / READY FOOD: Frozen meals, cup noodles, instant food, canned goods -> Division "01" (Food e.g. "01.1.9" or "01.1.1"), NEVER Division 11 (Restaurants).
- ALCOHOLIC BEVERAGES: Beer -> "02.1.3", Wine -> "02.1.2", Spirits -> "02.1.1", Cigarettes -> "02.2.0", NEVER Division 01.
- BABY FORMULA & BABY FOOD: Division "01" (e.g. "01.1.4" for milk/formula or "01.1.9").
- CLEANING AGENTS: Detergent, dish soap, bleach, floor cleaner -> "05.6.1" (Non-durable household goods).
- PHARMACEUTICALS & HEALTH: Medicines, vitamins, pain relief -> "06.1.1", Balms, masks, bandages -> "06.1.2".

Return ONLY a JSON array of objects with the exact schema:
[
  {
    "id": "<string or int matching input id>",
    "coicop_division": "<2-digit division e.g. 01>",
    "coicop_code": "<4-digit class code e.g. 01.1.1>",
    "confidence": <float>,
    "reason": "<short justification under 10 words>"
  }
]
"""


class GeminiCOICOPClassifier:
    """Direct, high-performance batch COICOP classifier powered by Google Gemini."""

    def __init__(self, db_conn_str: str | None = None, model_name: str | None = None) -> None:
        register_uuid()
        self.db_conn_str = db_conn_str or get_database_url()
        self.model_name = model_name or DEFAULT_MODEL
        self.key_pool = GeminiKeyPool()
        log.info(
            "GeminiCOICOPClassifier initialized with model %s and %d keys.",
            self.model_name,
            self.key_pool.get_key_count(),
        )

    def _get_connection(self):
        from pipeline.config import alternate_host_url
        conn_str = self.db_conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)
        try:
            conn = psycopg2.connect(conn_str)
        except psycopg2.OperationalError:
            conn = psycopg2.connect(alternate_host_url(conn_str))
        register_uuid(conn_or_curs=conn)
        return conn

    def _call_gemini_batch(self, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Invokes Gemini with a batch of products and parses structured JSON output.

        Resilience features:
        - Exponential backoff with jitter for transient failures.
        - Longer backoff for 503 (server overload) vs general errors.
        - Key rotation on 429 rate-limit errors.
        - Automatic fallback to FALLBACK_MODEL when primary model exhausts retries.
        """
        if not HAS_GENAI or genai is None:
            log.error("google-genai library not available.")
            return {}

        api_key = self.key_pool.get_next_key()
        if not api_key:
            log.error("No active Gemini API key available.")
            return {}

        client = genai.Client(api_key=api_key)
        prompt_data = [
            {
                "id": str(item["id"]),
                "name": item.get("name", ""),
                "brand": item.get("brand", "") or "",
            }
            for item in items
        ]

        prompt_str = "Classify the following products into UN COICOP:\n" + json.dumps(
            prompt_data, ensure_ascii=False, indent=2
        )

        results: dict[str, dict[str, Any]] = {}

        models_to_try = [self.model_name]
        if FALLBACK_MODEL and FALLBACK_MODEL != self.model_name:
            models_to_try.append(FALLBACK_MODEL)

        for model_idx, current_model in enumerate(models_to_try):
            if model_idx > 0:
                log.info("Falling back to model %s for batch of %d items.", current_model, len(items))
                # Get a fresh key for the fallback attempt
                api_key = self.key_pool.get_next_key()
                if api_key:
                    client = genai.Client(api_key=api_key)

            for attempt in range(MAX_RETRIES):
                try:
                    config = genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.1,
                    )
                    response = client.models.generate_content(
                        model=current_model,
                        contents=prompt_str,
                        config=config,
                    )
                    resp_text = response.text.strip()
                    if resp_text.startswith("```"):
                        resp_text = re.sub(r"^```(?:json)?\s*", "", resp_text)
                        resp_text = re.sub(r"\s*```$", "", resp_text)

                    parsed = json.loads(resp_text)
                    if isinstance(parsed, list):
                        for obj in parsed:
                            item_id = str(obj.get("id"))
                            raw_div = str(obj.get("coicop_division", "01")).zfill(2)
                            code = str(obj.get("coicop_code", f"{raw_div}.1.1"))
                            conf = float(obj.get("confidence", 0.95))
                            # Enforce strict 4-digit class code (DD.G.C)
                            parts = code.split('.')
                            if len(parts) > 3:
                                code = '.'.join(parts[:3])
                            elif len(parts) == 2:
                                code = f"{code}.1"

                            results[item_id] = {
                                "coicop_division": raw_div,
                                "coicop_code": code,
                                "confidence": conf,
                                "reason": obj.get("reason", "gemini_classified"),
                            }
                    return results  # Success — return immediately
                except Exception as e:
                    err_str = str(e).lower()
                    is_503 = "503" in err_str or "unavailable" in err_str
                    is_429 = "429" in err_str or "resourceexhausted" in err_str or "quota" in err_str

                    log.warning(
                        "Gemini classification batch failed (model=%s, attempt %d/%d): %s",
                        current_model, attempt + 1, MAX_RETRIES, e,
                    )

                    if is_429:
                        # Rate-limited: rotate to a different API key and cool down current one
                        self.key_pool.mark_key_rate_limited(api_key)
                        api_key = self.key_pool.get_next_key()
                        if api_key:
                            client = genai.Client(api_key=api_key)

                    if is_503:
                        # Server overload: longer exponential backoff (base 3s)
                        backoff = min(3.0 * (2 ** attempt) + random.uniform(0, 2.0), 60.0)
                    else:
                        # General error: standard exponential backoff (base 2s)
                        backoff = min(2.0 * (2 ** attempt) + random.uniform(0, 1.0), 30.0)

                    log.info("Retrying in %.1fs...", backoff)
                    time.sleep(backoff)

            # All retries exhausted for this model — try next model if available
            log.warning(
                "All %d retries exhausted for model %s. %s",
                MAX_RETRIES, current_model,
                "Trying fallback model..." if model_idx < len(models_to_try) - 1 else "No more models to try.",
            )

        return results

    def classify_single(self, name: str, brand: str | None = None) -> dict[str, Any]:
        """Classifies a single product for immediate inline creation."""
        results = self._call_gemini_batch([{"id": "0", "name": name, "brand": brand}])
        if "0" in results:
            return results["0"]
        return {
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "confidence": 0.5,
            "reason": "fallback_default",
        }

    def classify_unclassified_canonical_items(
        self, limit: int = 500, scrape_date: str | None = None
    ) -> dict[str, int]:
        """Finds items that need classification (prioritizing NULL coicop_code and today's new items)."""
        conn = self._get_connection()
        stats = {"total_found": 0, "classified": 0, "failed": 0}

        try:
            with conn.cursor() as cur:
                if scrape_date:
                    limit_clause = f"LIMIT {int(limit)}" if (limit and limit > 0) else ""
                    cur.execute(
                        f"""
                        SELECT DISTINCT ci.item_id, ci.canonical_name, ci.brand
                        FROM silver.canonical_items ci
                        LEFT JOIN silver.item_match_log iml ON ci.item_id = iml.item_id
                        WHERE (
                            (iml.matched_at::date = %s::date AND iml.match_method = 'new_item')
                            OR ci.coicop_code LIKE '%%.unclassified'
                            OR ci.coicop_code IS NULL 
                            OR ci.coicop_division IS NULL
                            OR array_length(string_to_array(ci.coicop_code, '.'), 1) < 3
                        )
                        {limit_clause};
                        """,
                        (scrape_date,),
                    )
                else:
                    limit_clause = f"LIMIT {int(limit)}" if (limit and limit > 0) else "LIMIT 2000"
                    cur.execute(
                        f"""
                        SELECT item_id, canonical_name, brand
                        FROM silver.canonical_items
                        WHERE coicop_code IS NULL 
                           OR coicop_division IS NULL
                           OR coicop_code LIKE '%%.unclassified'
                           OR array_length(string_to_array(coicop_code, '.'), 1) < 3
                        {limit_clause};
                        """
                    )
                rows = cur.fetchall()

            stats["total_found"] = len(rows)
            if not rows:
                log.info("No unclassified items found for classification.")
                return stats

            log.info("Classifying %d unclassified canonical items with Gemini AI...", len(rows))

            items_to_process = [
                {"id": str(r[0]), "name": r[1], "brand": r[2]} for r in rows
            ]

            batches = [
                items_to_process[i : i + BATCH_SIZE]
                for i in range(0, len(items_to_process), BATCH_SIZE)
            ]

            max_workers = max(1, min(self.key_pool.get_key_count() or 4, 8))
            log.info("Processing %d batches using %d parallel workers...", len(batches), max_workers)

            update_tuples: list[tuple[str, str, str, float, str]] = []

            def _process_one_batch(b: list[dict[str, Any]]) -> tuple[list[tuple[str, str, str, float, str]], int, int]:
                decisions = self._call_gemini_batch(b)
                tuples = []
                c_count = 0
                f_count = 0
                for item in b:
                    item_id_str = item["id"]
                    if item_id_str in decisions:
                        dec = decisions[item_id_str]
                        tuples.append((
                            dec["coicop_division"],
                            dec["coicop_code"],
                            "gemini_ai",
                            float(dec.get("confidence", 0.95)),
                            item_id_str,
                        ))
                        c_count += 1
                    else:
                        f_count += 1
                return tuples, c_count, f_count

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_batch = {executor.submit(_process_one_batch, b): b for b in batches}
                for future in as_completed(future_to_batch):
                    try:
                        tuples, c_count, f_count = future.result()
                        update_tuples.extend(tuples)
                        stats["classified"] += c_count
                        stats["failed"] += f_count
                    except Exception as e:
                        log.warning("Parallel batch classification worker error: %s", e)
                        stats["failed"] += len(future_to_batch[future])

            if update_tuples:
                with conn.cursor() as cur:
                    execute_batch(
                        cur,
                        """
                        UPDATE silver.canonical_items
                        SET coicop_division = %s,
                            coicop_code = %s,
                            coicop_method = %s,
                            coicop_confidence = %s,
                            coicop_classified_at = NOW()
                        WHERE item_id = %s::uuid;
                        """,
                        update_tuples,
                        page_size=200,
                    )
                conn.commit()
                log.info("Successfully updated %d canonical items with COICOP codes.", len(update_tuples))

            return stats
        finally:
            conn.close()
