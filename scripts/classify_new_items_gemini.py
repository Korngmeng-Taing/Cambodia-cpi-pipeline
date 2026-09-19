#!/usr/bin/env python3
"""
scripts/classify_new_items_gemini.py
─────────────────────────────────────
Re-classifies all 38,376 new items NOT in silver.canonical_items using Gemini AI.
Loads new items from clean_store_prices, classifies them, and adds them to canonical_items.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from psycopg2.extras import execute_values
from psycopg2 import extensions as pg_ext
pg_ext.register_adapter(uuid.UUID, lambda val: pg_ext.AsIs(str(val)))
from pipeline.config import get_db_connection
from pipeline.key_pool import GeminiKeyPool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("classify_new_items")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
DEFAULT_BATCH_SIZE = 50
DEFAULT_DELAY = 0.5
MAX_RETRIES = 5
TIMEOUT_SECONDS = 45

# ── 48 Official Cambodia CPI 2018 Classes ──────────────────────────────
OFFICIAL_CLASSES: dict[str, str] = {
    "01.1.1": "Bread and cereals (Rice, flour, noodles, bread, baby cereal)",
    "01.1.2": "Meat (Beef, pork, poultry, duck)",
    "01.1.3": "Fish and seafood (Fresh, dried, processed fish, shrimp, crab)",
    "01.1.4": "Milk, cheese and eggs (Dairy, fresh milk, infant formula milk)",
    "01.1.5": "Oils and fats (Cooking oil, vegetable oil, lard)",
    "01.1.6": "Fruit (Fresh and preserved fruit)",
    "01.1.7": "Vegetables (Fresh, frozen, canned vegetables, potatoes)",
    "01.1.8": "Sugar, jam, honey, chocolate, cookies, snacks, confectionery, nuts",
    "01.1.9": "Food products n.e.c. (Salt, fish sauce, soy sauce, spices, broth, soup base, culinary vinegar)",
    "01.2.1": "Coffee, tea and cocoa",
    "01.2.2": "Mineral waters, soft drinks, fruit and vegetable juices",
    "02.1.1": "Spirits and liqueurs (Whisky, brandy, vodka)",
    "02.1.2": "Wine (Red wine, white wine, champagne)",
    "02.1.3": "Beer (Lager, draft, stout, Angkor beer, alcoholic cider)",
    "02.2.0": "Tobacco (Cigarettes, cigars, rolling tobacco)",
    "03.1.2": "Garments (Men, women, children clothing)",
    "03.1.3": "Other articles of clothing and clothing accessories",
    "03.2.1": "Shoes and other footwear",
    "04.1.1": "Actual rentals paid by tenants (Apartments, villas, condos for rent)",
    "04.3.1": "Materials for the maintenance and repair of the dwelling",
    "04.4.1": "Water supply (Municipal piped tap water)",
    "04.5.1": "Electricity (EDC grid power)",
    "04.5.2": "Gas (LPG cooking gas cylinder refill)",
    "04.5.4": "Solid fuels (Firewood, charcoal)",
    "05.1.1": "Furniture and furnishings (Tables, chairs, beds, decorative items)",
    "05.2.1": "Household textiles (Bedsheets, blankets, towels, tablecloths)",
    "05.5.1": "Glassware, tableware and household utensils (Cookware, pots, pans, water bottles)",
    "05.6.1": "Non-durable household goods (Detergent, cleaners, paper napkins, candles)",
    "06.1.1": "Pharmaceutical products (Medicines, painkillers, antibiotics, medical creams)",
    "06.1.2": "Other medical products (Bandages, medicated balm, thermometers)",
    "06.2.1": "Medical services (Doctor consultation, clinic visit)",
    "07.1.2": "Motorcycles (Motorbikes, scooters)",
    "07.2.2": "Fuels and lubricants (Super 95, Regular gasoline, Diesel)",
    "07.2.3": "Maintenance and repair of personal transport equipment",
    "07.3.2": "Passenger transport by bus, coach and van (Bus tickets)",
    "08.2.0": "Telephone equipment (Smartphones, cellular handsets, phone accessories, chargers)",
    "08.3.0": "Telephone and internet services (SIM cards, mobile data, broadband wifi)",
    "09.1.1": "Equipment for reception/recording of sound and pictures (TV, audio)",
    "09.1.3": "Information processing equipment (Laptops, PCs, tablets)",
    "09.3.1": "Games, toys and hobbies (Toys, board games, puzzles, sports equipment, camping gear, fitness equipment)",
    "09.5.1": "Books and stationery (Textbooks, notebooks, pens, copy paper)",
    "10.1.0": "Education services (Tuition fees ONLY - never physical stationery)",
    "11.1.1": "Restaurants, cafes and the like (Dining out, fast food - never supermarkets)",
    "11.2.0": "Accommodation services (Hotels, motels, guesthouses)",
    "12.1.1": "Hairdressing salons and personal grooming establishments",
    "12.1.3": "Personal care products (Toothpaste, soap, cosmetics, skincare, perfumes, diapers, hair dryers, nail files, hair rollers, trimmers)",
    "12.3.1": "Jewellery, clocks and watches",
    "12.3.2": "Other personal effects (Bags, luggage, wallets)",
}

SUPERMARKET_STORES = {"aeon", "aeon3", "delishop", "grab_lucky", "grab_chipmong", "l192"}

VALID_CLASSES_PROMPT = "\n".join(f"- {c}: {desc}" for c, desc in OFFICIAL_CLASSES.items())

SYSTEM_PROMPT = f"""You are an expert economic statistician classifying consumer goods for Cambodia Consumer Price Index (CPI) according to UN COICOP 2018.

You must map each product into EXACTLY ONE of the following valid COICOP codes:
{VALID_CLASSES_PROMPT}

MANDATORY CPI RULES:
1. Physical stationery (notebooks, pens, paper, rulers, staplers) MUST be classified as '09.5.1' (Books and stationery), NEVER '10.1.0' (which is strictly tuition fees).
2. Supermarkets (aeon, delishop, l192, grab_lucky, grab_chipmong) CANNOT sell '11.1.1' (restaurants) or '11.2.0' (hotels). Ready meals, sushi, bentos sold in stores are '01.1.1' or '01.1.2'.
3. Culinary vinegars (apple cider vinegar, wine vinegar) and broths/soup bases are '01.1.9' (Seasonings), NOT alcohol or kitchenware.
4. Brand snacks like Bourbon Petit cookies and Camel roasted nuts are '01.1.8' (Confectionery/Snacks), NOT alcohol or tobacco.
5. Baby formula is '01.1.4' (Milk/Dairy). Baby cereals/biscuits are '01.1.1'. Baby purees are '01.1.9'. Diapers/wipes are '12.1.3'.
6. Skincare, shower gels, cleansing oils, and perfumes are '12.1.3' (Personal care), NOT clothing or cooking oil.
7. Hair care tools (nail files, hair rollers, hair trimmers, hair clippers, nose trimmers) are '12.1.3' (Personal care products), NOT '12.1.1' (which is for salon services only).
8. Sports equipment, camping gear, fitness equipment, yoga mats, bicycles, swimming gear are '09.3.1' (Games, toys and hobbies / sports equipment).
9. Phone accessories (phone cases, cooling fans, stands, chargers) are '08.2.0'.
10. Kitchenware (frying pans, pots, knives, water bottles, tableware) are '05.5.1'.
"""


def call_gemini_rest(prompt: str, key: str, model_name: str = DEFAULT_MODEL) -> list[dict[str, Any]]:
    """Calls Gemini via direct HTTPS REST endpoint with JSON output mode."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        res = json.loads(response.read().decode("utf-8"))
        raw_text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict) and "items" in parsed:
            return parsed["items"]
        else:
            return [parsed]


def process_batch_with_retry(
    items_batch: list[dict[str, Any]],
    pool: GeminiKeyPool,
    model_name: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    """Sends a batch of items to Gemini with key rotation and retry logic."""
    clean_items = [
        {
            "id": it["item_id"],
            "name": it["name_clean"],
            "stores": it["store_slug"],
        }
        for it in items_batch
    ]

    prompt = f"""{SYSTEM_PROMPT}

Classify each of the following {len(clean_items)} products.
Input products:
{json.dumps(clean_items, ensure_ascii=False)}

Return a JSON array of objects with keys:
- "id": product id
- "coicop_code": valid COICOP code from the list
- "confidence": confidence score (0.0 to 1.0)
- "reasoning": brief explanation (under 12 words)
"""

    for attempt in range(1, MAX_RETRIES + 1):
        key = pool.get_next_key()
        if not key:
            log.error("No active API keys available in pool.")
            break
        try:
            results = call_gemini_rest(prompt, key, model_name)
            return results
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="ignore")[:200]
            retry_after = int(err.headers.get("Retry-After", "0")) if err.headers.get("Retry-After") else 0
            if err.code in (429, 503, 500):
                if err.code == 429:
                    pool.mark_key_rate_limited(key)
                wait = retry_after if retry_after > 0 else 2.0 * attempt
                log.warning("HTTP %d (Attempt %d/%d): %s. Waiting %.1fs. Cooling key...", err.code, attempt, MAX_RETRIES, err_body, wait)
                time.sleep(wait)
            else:
                log.error("HTTP %d error: %s", err.code, err_body)
                break
        except Exception as exc:
            log.warning("Request failed (Attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
            time.sleep(2.0 * attempt)

    return []


def validate_and_guard(
    prediction: dict[str, Any],
    name_clean: str,
    store_slug: str,
) -> tuple[str, str, float, str]:
    """
    Validates Gemini output and enforces Cambodia CPI domain guardrails.
    Returns (coicop_division, coicop_code, confidence, reasoning).
    """
    code = str(prediction.get("coicop_code", "01.1.9")).strip()
    conf = float(prediction.get("confidence", 0.90))
    reasoning = str(prediction.get("reasoning", "gemini_ai"))
    name_lower = name_clean.lower() if name_clean else ""
    stores = {s.lower().strip() for s in [store_slug] if s}

    # Fallback if unknown code returned
    if code not in OFFICIAL_CLASSES:
        div = code[:2]
        if div in ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]:
            matches = [c for c in OFFICIAL_CLASSES if c.startswith(div)]
            code = matches[0] if matches else f"{div}.1.1"
        else:
            code = "01.1.9"

    # Guardrail 1: Physical Stationery -> 09.5.1 (Division 10 is tuition fees only)
    stationery_words = ["notebook", "pen", "pencil", "paper", "ruler", "eraser", "stapler",
                        "marker", "folder", "binder", "highlighter", "scissors", "glue",
                        "calculator", "compass", "envelope", "whiteboard", "sketchbook"]
    if code.startswith("10.") and any(w in name_lower for w in stationery_words):
        code = "09.5.1"
        reasoning = "guardrail_stationery_to_0951"

    # Guardrail 2: Supermarkets cannot sell 11.x or 04.x
    if stores and stores.issubset(SUPERMARKET_STORES):
        if code.startswith("11."):
            code = "01.1.9"
            reasoning = "guardrail_supermarket_no_11"
        elif code.startswith("04."):
            if any(w in name_lower for w in ["pan", "pot", "plate", "mug", "glass", "fork", "spoon", "bottle"]):
                code = "05.5.1"
            else:
                code = "05.6.1"
            reasoning = "guardrail_supermarket_no_04"

    # Guardrail 3: Vinegars / Broths -> 01.1.9
    vinegar_broth_words = ["vinegar", "cider vinegar", "wine vinegar", "rice vinegar",
                           "broth", "soup base", "bouillon", "dashi", "stock cube",
                           "hot pot base", "tom yum paste"]
    if any(w in name_lower for w in vinegar_broth_words) and "cleaning vinegar" not in name_lower:
        if code != "01.1.9":
            code = "01.1.9"
            reasoning = "guardrail_vinegar_broth_to_0119"

    # Guardrail 4: Diapers / Baby wipes -> 12.1.3
    if any(w in name_lower for w in ["diaper", "drypant", "dry pants", "pampers", "huggies", "baby wipes", "wet wipes"]):
        code = "12.1.3"
        reasoning = "guardrail_diapers_to_1213"

    # Guardrail 5: Hair care tools -> 12.1.3 (not 12.1.1 which is salon services)
    hair_tools = ["nail file", "hair roller", "hair trimmer", "hair clipper", "nose trimmer",
                  "hair cutter", "manicure", "pedicure"]
    if any(w in name_lower for w in hair_tools):
        code = "12.1.3"
        reasoning = "guardrail_hair_tools_to_1213"

    # Guardrail 6: Sports/camping/fitness equipment -> 09.3.1
    sports_words = ["sports", "fitness", "camping", "yoga", "gym", "bicycle", "bike", "skateboard",
                    "skipping rope", "dumbbell", "yoga mat", "camping chair", "tent", "swimming",
                    "badminton", "tennis", "basketball", "soccer", "football", "volleyball",
                    "ping pong", "table tennis", "boxing", "golf", "archery", "exercise"]
    if any(w in name_lower for w in sports_words) and code not in ["09.3.1", "07.1.2", "07.2.2", "07.2.3", "07.3.2"]:
        if not code.startswith(("07", "08", "05.5")):
            code = "09.3.1"
            reasoning = "guardrail_sports_to_0931"

    # Guardrail 7: Phone accessories -> 08.2.0
    if any(w in name_lower for w in ["phone case", "cooling fan", "screen protector", "phone holder", "power bank", "charger cable"]):
        code = "08.2.0"
        reasoning = "guardrail_phone_acc_to_0820"

    division = code.split(".")[0]
    return division, code, conf, reasoning


def load_new_items(conn) -> list[dict[str, Any]]:
    """Loads all items from clean_store_prices that are NOT in canonical_items."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (csp.item_id)
            csp.item_id,
            csp.name_clean,
            csp.store_slug,
            csp.barcode,
            csp.coicop_code as current_code,
            csp.coicop_method as current_method
        FROM silver.clean_store_prices csp
        WHERE csp.item_id NOT IN (SELECT CAST(item_id AS text) FROM silver.canonical_items)
        AND csp.name_clean IS NOT NULL
        ORDER BY csp.item_id, csp.scraped_at DESC
    """)
    items = []
    for r in cur.fetchall():
        items.append({
            "item_id": r[0],
            "name_clean": r[1],
            "store_slug": r[2],
            "barcode": r[3],
            "current_code": r[4],
            "current_method": r[5],
        })
    return items


def commit_new_items(
    cur, conn, cache_records, new_items_dict
):
    """Commits new items to silver.canonical_items and silver.dim_coicop_ai_cache."""
    if not cache_records and not new_items_dict:
        return

    try:
        # Deduplicate cache_records by product_name (keep highest confidence)
        cache_dict = {}
        for name, code, conf, reasoning, model in cache_records:
            if name not in cache_dict or conf > cache_dict[name][2]:
                cache_dict[name] = (name, code, conf, reasoning, model)
        unique_cache = list(cache_dict.values())

        # Insert into dim_coicop_ai_cache using ON CONFLICT DO NOTHING
        if unique_cache:
            execute_values(
                cur,
                """
                INSERT INTO silver.dim_coicop_ai_cache
                    (product_name, coicop_code, confidence_score, reasoning, model_version)
                VALUES %s
                ON CONFLICT (product_name) DO NOTHING;
                """,
                unique_cache,
                page_size=2000,
            )

        # Deduplicate new_items_dict by item_id
        unique_new = {}
        for val in new_items_dict.values():
            iid = val[0]
            if iid not in unique_new:
                unique_new[iid] = val

        # Insert into silver.canonical_items
        if unique_new:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S+00:00')
            insert_data = [
                (uuid.UUID(item_id), name, "gemini_ai", div, code, conf, now_str)
                for item_id, name, div, code, conf, reasoning in unique_new.values()
            ]
            execute_values(
                cur,
                """
                INSERT INTO silver.canonical_items
                    (item_id, canonical_name, coicop_method, coicop_division, coicop_code, coicop_confidence, coicop_classified_at)
                VALUES %s
                ON CONFLICT (item_id) DO NOTHING;
                """,
                insert_data,
                page_size=2000,
            )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.error("Failed to commit checkpoint: %s", exc)
        raise exc


def run(execute: bool = False, sample_size: int | None = None, limit: int | None = None,
         batch_size: int = DEFAULT_BATCH_SIZE, max_workers: int = 4, model_name: str = DEFAULT_MODEL,
         delay: float = DEFAULT_DELAY):
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    log.info("Loading new items from clean_store_prices...")
    items = load_new_items(conn)
    log.info("Total new items to classify: %d", len(items))

    if sample_size and sample_size > 0:
        items = items[:sample_size]
        log.info("Sampling active: limited to %d items.", len(items))
    elif limit and limit > 0:
        items = items[:limit]
        log.info("Limit active: limited to %d items.", len(items))

    pool = GeminiKeyPool()
    if pool.get_key_count() == 0:
        log.error("No Gemini API keys found. Exiting.")
        return

    workers = min(max_workers, pool.get_key_count())
    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    log.info("Processing %d items in %d batches (batch_size=%d, workers=%d, model=%s)...",
             len(items), len(batches), batch_size, workers, model_name)

    classified_results: dict[str, tuple[str, str, float, str]] = {}
    pending_cache: list[tuple[str, str, float, str, str]] = []
    pending_new_items: dict[str, tuple[str, str, str, str, float, str]] = {}

    start_time = time.time()
    completed_batches = 0
    checkpoint_interval = 10

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_batch = {
            executor.submit(process_batch_with_retry, batch, pool, model_name): batch
            for batch in batches
        }

        for future in as_completed(future_to_batch):
            completed_batches += 1
            batch = future_to_batch[future]
            try:
                raw_preds = future.result()
                preds_by_id = {str(p.get("id")): p for p in raw_preds if "id" in p}

                for it in batch:
                    item_id = it["item_id"]
                    if item_id in preds_by_id:
                        p = preds_by_id[item_id]
                        div, code, conf, reasoning = validate_and_guard(p, it["name_clean"], it["store_slug"])
                    else:
                        div = it["current_code"][:2] if it["current_code"] else "01"
                        code = it["current_code"] if it["current_code"] else "01.1.9"
                        conf = 0.85
                        reasoning = "baseline_preserved"

                    res = (div, code, conf, reasoning)
                    classified_results[item_id] = res
                    pending_cache.append((
                        it["name_clean"],
                        code,
                        conf,
                        reasoning,
                        model_name,
                    ))
                    pending_new_items[item_id] = (item_id, it["name_clean"], div, code, conf, reasoning)

                if execute and completed_batches % checkpoint_interval == 0:
                    commit_new_items(cur, conn, pending_cache, pending_new_items)
                    log.info("Checkpoint: committed %d items to canonical_items & ai_cache.", len(pending_new_items))
                    pending_cache.clear()
                    pending_new_items.clear()

                time.sleep(delay)

                if completed_batches % 5 == 0 or completed_batches == len(batches):
                    elapsed = time.time() - start_time
                    items_done = len(classified_results)
                    rate = items_done / elapsed if elapsed > 0 else 0
                    log.info("Progress: %d/%d batches (%d items, %.1f items/s)",
                             completed_batches, len(batches), items_done, rate)

            except Exception as exc:
                log.error("Batch error: %s", exc)

    if execute and (pending_cache or pending_new_items):
        commit_new_items(cur, conn, pending_cache, pending_new_items)
        log.info("Final checkpoint committed.")

    log.info("Gemini classification complete in %.1fs.", time.time() - start_time)
    log.info("Total items classified: %d", len(classified_results))

    if not execute:
        log.info("DRY RUN completed. Run with --execute to commit to PostgreSQL.")
        conn.close()
        return

    # Synchronize clean_store_prices for newly added canonical_items
    log.info("Synchronizing clean_store_prices for new items...")
    cur.execute("""
        UPDATE silver.clean_store_prices s
        SET 
            coicop_division = ci.coicop_division,
            coicop_code = ci.coicop_code,
            coicop_method = ci.coicop_method,
            coicop_confidence = ci.coicop_confidence
        FROM silver.canonical_items ci
        WHERE s.item_id::text = ci.item_id::text
          AND ci.coicop_method = 'gemini_ai'
          AND (
              s.coicop_division IS DISTINCT FROM ci.coicop_division OR
              s.coicop_code IS DISTINCT FROM ci.coicop_code
          );
    """)
    synced = cur.rowcount
    conn.commit()
    log.info("Synchronized %d observations in clean_store_prices.", synced)

    # Verify
    cur.execute("SELECT COUNT(*) FROM silver.canonical_items")
    total = cur.fetchone()[0]
    log.info("Total canonical_items now: %d", total)

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Re-classify new items with Gemini AI")
    parser.add_argument("--execute", action="store_true", help="Commit changes to PostgreSQL")
    parser.add_argument("--sample", type=int, default=None, help="Sample N items to test")
    parser.add_argument("--limit", type=int, default=None, help="Limit to N items")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size per API call")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Gemini model name")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay in seconds between batches (default 0.5s)")
    args = parser.parse_args()

    run(
        execute=args.execute,
        sample_size=args.sample,
        limit=args.limit,
        batch_size=args.batch_size,
        max_workers=args.workers,
        model_name=args.model,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
