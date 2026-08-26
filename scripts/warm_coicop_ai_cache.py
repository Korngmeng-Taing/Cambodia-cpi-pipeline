#!/usr/bin/env python3
"""
Bulk Offline Gemini AI COICOP Cache Warmer.

Efficiently streams uncached distinct canonical products from silver.canonical_items,
sends them in high-density structured JSON batches (50 items/call) to Gemini, and
upserts the results immediately into silver.dim_coicop_ai_cache.

Usage:
    # Warm next 500 items:
    python scripts/warm_coicop_ai_cache.py --limit 500

    # Warm 2000 items with custom delay:
    python scripts/warm_coicop_ai_cache.py --limit 2000 --delay 1.5

    # Run continuously until entire catalog is classified:
    python scripts/warm_coicop_ai_cache.py --limit 0
"""

import argparse
import json
import logging
import os
import re
import time
from typing import Any

from sqlalchemy import create_engine, text

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ai_cache_warmer")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BATCH_SIZE = 50
RATE_LIMIT_BACKOFF_SECONDS = 25.0
UNCLASSIFIED = "99.9.9"

SYSTEM_PROMPT = """You are an expert statistical classifier for the UN COICOP 2018 taxonomy (Classification of Individual Consumption According to Purpose). I will give you a list of e-commerce product names from Cambodia. You must return a JSON array mapping each product to its most specific 5-digit COICOP code. If unsure, return '99.9.9'. Include a 'confidence_score' (0.0 to 1.0) and a brief 'reasoning' string.

Classification rules:
- Use the official dotted 5-digit COICOP 2018 notation, e.g. '01.1.1' (Bread and cereals) or '07.2.2' (Fuels and lubricants).
- Prefer the MOST SPECIFIC code the name unambiguously supports.
- If the product cannot be confidently mapped to any COICOP class, return '99.9.9'.
- 'product_name' in the response MUST exactly match the input name.
- 'confidence_score' must be a float from 0.0 to 1.0.
- 'reasoning' must be a short (max 15 words) English explanation.

Major COICOP 2018 Divisions:
- 01: Food and non-alcoholic beverages (01.1.1 Cereals/bread/rice/noodles, 01.1.2 Meat, 01.1.3 Fish/seafood, 01.1.4 Milk/cheese/eggs, 01.1.5 Oils/fats, 01.1.6 Fruits, 01.1.7 Vegetables/sauces/condiments, 01.1.8 Sugar/chocolate/confectionery/cookies/sweets, 01.2.1 Coffee/tea/cocoa, 01.2.2 Water/soft drinks/juices)
- 02: Alcoholic beverages & tobacco (02.1.1 Spirits/whiskey/vodka/liquor, 02.1.2 Wine, 02.1.3 Beer/cider, 02.2.1 Tobacco/cigarettes/cigars)
- 03: Clothing and footwear (03.1.1 Men's clothing, 03.1.2 Women's clothing, 03.1.3 Children's clothing, 03.2.1 Shoes/footwear)
- 04: Housing, water, electricity, gas and other fuels (04.1.1 Actual rentals for housing, 04.5.1 Electricity, 04.5.2 Gas LPG, 04.4.1 Water supply)
- 05: Furnishings, household equipment and routine household maintenance (05.1.1 Furniture, 05.2.1 Household textiles/bedding, 05.3.1 Major household appliances, 05.4.1 Small electric appliances, 05.5.1 Glassware/cookware/tableware/kitchen utensils, 05.6.1 Cleaning products/detergents/toilet paper/sponges)
- 06: Health (06.1.1 Pharmaceuticals/medicines/pain relief/antibiotics, 06.1.2 Other medical products/first aid/balms/drops/plasters, 06.2.1 Outpatient medical services, 06.2.2 Dental services)
- 07: Transport (07.1.1 Purchase of motor vehicles, 07.2.2 Fuels and lubricants/petrol/diesel/gasoline, 07.3.2 Passenger transport by bus/coach/van)
- 08: Information and communication (08.2.0 Telephone equipment/smartphones/chargers, 08.3.0 Internet connection services/wifi, 08.4.0 Mobile cellular plans/services)
- 09: Recreation, sport and culture (09.1.1 Audio-visual/cameras/speakers/headphones, 09.3.1 Games/toys/video games/consoles, 09.3.4 Pets & pet food, 09.5.4 Stationery/drawing/notebooks/pens)
- 10: Education services (10.1.1 Primary education, 10.2.1 Secondary education, 10.4.1 Higher education)
- 11: Restaurants and accommodation services (11.1.1 Restaurants/cafes/meals, 11.2.0 Accommodation services/hotel rooms)
- 12: Insurance and financial services (12.1.1 Life insurance, 12.1.2 Non-life/health/travel insurance)
- 13: Personal care, social protection and miscellaneous goods (13.1.1 Hair care/shampoos, 13.1.2 Personal grooming/skincare/lotions/perfumes/deodorants/cosmetics, 13.2.1 Jewelry/watches, 13.2.9 Other personal effects/bags/wallets)

Response format: Strict JSON array, e.g.:
[{"product_name": "<exact input name>", "coicop_code": "01.1.4", "confidence_score": 0.95, "reasoning": "Fresh whole milk"}]
"""


def get_engine():
    from pipeline.config import get_database_url

    conn_str = get_database_url()
    if "localhost" in conn_str and os.path.exists("/.dockerenv"):
        conn_str = conn_str.replace("localhost", "postgres")
    return create_engine(conn_str)


class GeminiModelPool:
    """Manages a pool of Gemini API keys with round-robin rotation and automatic quota failover."""

    def __init__(self, keys: list[str], model_name: str = DEFAULT_MODEL):
        self.keys = list(keys)
        self.model_name = model_name
        self.exhausted_keys: set[str] = set()
        self._current_idx = 0

    @property
    def active_keys(self) -> list[str]:
        return [k for k in self.keys if k not in self.exhausted_keys]

    def mark_exhausted(self, key: str):
        self.exhausted_keys.add(key)
        log.warning(
            "Gemini API key (%s...) exhausted. %d active key(s) remaining in pool.",
            key[:12] if len(key) >= 12 else key,
            len(self.active_keys),
        )

    def generate_content(self, contents, **kwargs):
        if genai is None:
            raise RuntimeError("google-generativeai is required (pip install google-generativeai)")
        active = self.active_keys
        if not active:
            raise RuntimeError("All Gemini API keys in the pool have been exhausted.")

        last_exc = None
        for _ in range(len(active)):
            active = self.active_keys
            if not active:
                break
            key = active[self._current_idx % len(active)]
            self._current_idx += 1
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    generation_config=genai.GenerationConfig(response_mime_type="application/json"),
                )
                return model.generate_content(contents, **kwargs)
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                if "429" in msg or "ResourceExhausted" in msg or "quota" in msg.lower():
                    self.mark_exhausted(key)
                    if self.active_keys:
                        log.info(
                            "Failing over to next Gemini API key (%d active keys left)...",
                            len(self.active_keys),
                        )
                        continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("All Gemini API keys in the pool have been exhausted.")


def build_gemini_model(model_name: str):
    raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""
    api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not api_keys:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
    log.info("Initialized Gemini Model Pool with %d key(s): %s (JSON Mode)", len(api_keys), model_name)
    return GeminiModelPool(api_keys, model_name=model_name)


def fetch_uncached_products(engine, limit: int = 1000, scrape_date: str | None = None) -> list[str]:
    """Fetches unique product names active on scrape_date that do not yet exist in silver.dim_coicop_ai_cache."""
    limit_clause = f"LIMIT {limit}" if limit > 0 else ""
    date_filter = "p.scrape_date = CAST(:ds AS DATE)" if scrape_date else "p.scrape_date = (SELECT max(scrape_date) FROM staging.int_prices_cleaned)"
    
    query = text(
        f"""
        SELECT DISTINCT ci.canonical_name
        FROM (
            SELECT DISTINCT item_id, store_slug, scrape_date
            FROM staging.int_prices_cleaned p
            WHERE {date_filter}
              AND p.item_id IS NOT NULL
              AND p.store_slug NOT IN (
                  'communitypharma', 'khmer24', 'realestate',
                  'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk',
                  'bookmebus', 'redbus', 'redmebus', 'new_gasoline',
                  'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi',
                  'smart', 'smart_wifi'
              )
        ) p
        JOIN silver.canonical_items ci
          ON ci.item_id::text = p.item_id::text
        LEFT JOIN silver.dim_coicop_ai_cache ai 
          ON lower(regexp_replace(trim(ai.product_name), '\\s+', ' ', 'g')) = lower(regexp_replace(trim(ci.canonical_name), '\\s+', ' ', 'g'))
        WHERE (ai.coicop_code IS NULL OR ai.coicop_code = '99.9.9')
          AND ci.canonical_name IS NOT NULL
          AND length(trim(ci.canonical_name)) > 1
        ORDER BY ci.canonical_name
        {limit_clause}
        """
    )
    params = {"ds": scrape_date} if scrape_date else {}
    with engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [r[0] for r in rows]


def parse_json_response(raw_text: str) -> list[dict[str, Any]]:
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", clean)
        if match:
            parsed = json.loads(match.group(0))
        else:
            raise
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON list, got {type(parsed).__name__}")
    return parsed


def classify_batch_with_retry(model, names: list[str]) -> list[dict[str, Any]]:
    for attempt in range(1, 3):
        try:
            prompt_content = [SYSTEM_PROMPT] + [f"- {n}" for n in names]
            response = model.generate_content(prompt_content)
            return parse_json_response(response.text)
        except Exception as exc:
            msg = str(exc)
            if ("429" in msg or "ResourceExhausted" in msg or "quota" in msg.lower()) and attempt == 1:
                log.warning("Rate limit (429) hit. Backing off %.1fs...", RATE_LIMIT_BACKOFF_SECONDS)
                time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                continue
            if attempt == 2:
                log.error("Failed batch of %d items: %s", len(names), exc)
                return []
    return []


def upsert_batch_to_cache(engine, results: list[dict[str, Any]], model_name: str) -> int:
    valid = [
        r for r in results
        if r.get("product_name") and r.get("coicop_code") and r.get("coicop_code") != UNCLASSIFIED
    ]
    if not valid:
        return 0

    stmt = text(
        """
        INSERT INTO silver.dim_coicop_ai_cache
            (product_name, coicop_code, confidence_score, reasoning, model_version, classified_at)
        VALUES (:name, :coicop, :confidence, :reasoning, :model, CURRENT_TIMESTAMP)
        ON CONFLICT (product_name) DO UPDATE
        SET coicop_code = EXCLUDED.coicop_code,
            confidence_score = EXCLUDED.confidence_score,
            reasoning = EXCLUDED.reasoning,
            model_version = EXCLUDED.model_version,
            classified_at = CURRENT_TIMESTAMP
        """
    )

    with engine.begin() as conn:
        for row in valid:
            code = str(row["coicop_code"]).strip()
            if code.startswith("13."):
                code = "12." + code[3:]
            conn.execute(
                stmt,
                {
                    "name": str(row["product_name"]).strip(),
                    "coicop": code,
                    "confidence": round(float(row.get("confidence_score", 0.90)), 4),
                    "reasoning": str(row.get("reasoning", "")),
                    "model": model_name,
                },
            )
    return len(valid)


def main():
    parser = argparse.ArgumentParser(description="Bulk Offline Gemini AI COICOP Cache Warmer")
    parser.add_argument("--scrape-date", type=str, default=None, help="Specific scrape date (YYYY-MM-DD) to classify products for (defaults to latest/today)")
    parser.add_argument("--limit", type=int, default=0, help="Number of uncached items to process (0 = all today's items)")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of items per Gemini request")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to sleep between API calls")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Gemini model name")
    args = parser.parse_args()

    engine = get_engine()
    model = build_gemini_model(args.model)

    log.info("Fetching uncached candidate products for date=%s (limit=%d)...", args.scrape_date or "latest", args.limit)
    candidates = fetch_uncached_products(engine, limit=args.limit, scrape_date=args.scrape_date)
    total_candidates = len(candidates)
    log.info("Found %d uncached products ready for AI classification.", total_candidates)

    if not candidates:
        log.info("All products are already classified and cached! Exiting.")
        return

    batches = [candidates[i:i + args.batch_size] for i in range(0, total_candidates, args.batch_size)]
    total_batches = len(batches)
    log.info("Starting processing: %d total batches of up to %d items each.", total_batches, args.batch_size)

    start_time = time.time()
    total_upserted = 0

    for idx, batch in enumerate(batches, 1):
        batch_start = time.time()
        log.info(
            "[%d/%d] Sending batch of %d items (e.g. '%s')...",
            idx, total_batches, len(batch), batch[0][:40]
        )

        results = classify_batch_with_retry(model, batch)
        upserted = upsert_batch_to_cache(engine, results, args.model)
        total_upserted += upserted

        elapsed = time.time() - batch_start
        log.info(
            "[%d/%d] Successfully classified & cached %d/%d items (%.2fs) | Cumulative cached: %d",
            idx, total_batches, upserted, len(batch), elapsed, total_upserted
        )

        if idx < total_batches and args.delay > 0:
            time.sleep(args.delay)

    total_time = time.time() - start_time
    log.info("=" * 60)
    log.info("Bulk AI Cache Warming Complete!")
    log.info("Total Products Processed: %d", total_candidates)
    log.info("Total Products Cached:    %d", total_upserted)
    log.info("Total Execution Time:     %.1f seconds (%.2f items/sec)", total_time, total_upserted / max(total_time, 0.1))
    log.info("=" * 60)


if __name__ == "__main__":
    main()
