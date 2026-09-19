#!/usr/bin/env python3
"""
scripts/classify_catalog_gemini.py
──────────────────────────────────
One-Time Global Gemini AI Catalog Classifier for Cambodia CPI.

High-throughput, guarded batch classifier that sends distinct canonical products
to Google Gemini (gemini-3.1-flash-lite) using multi-key pool rotation,
structured JSON prompting, and strict post-processing domain guardrails.

Updates:
  1. silver.dim_coicop_ai_cache (permanent memoization cache)
  2. silver.canonical_items (authoritative product catalog)
  3. gold.dim_items (synchronized dimension table)
  4. silver.clean_store_prices (all historical price observations)

Usage:
  # Dry-run on a sample of 100 items:
  python scripts/classify_catalog_gemini.py --sample 100

  # Execute classification on next 500 items:
  python scripts/classify_catalog_gemini.py --limit 500 --execute

  # Execute full one-time classification across entire catalog:
  python scripts/classify_catalog_gemini.py --execute
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from psycopg2.extras import execute_values
from pipeline.config import get_db_connection
from pipeline.key_pool import GeminiKeyPool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("classify_catalog_gemini")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
DEFAULT_BATCH_SIZE = 50
MAX_RETRIES = 5
TIMEOUT_SECONDS = 45

# ── 48 Official Cambodia CPI 2018 Classes ──────────────────────────────────────
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
    "09.3.1": "Games, toys and hobbies (Toys, board games, puzzles)",
    "09.3.2": "Equipment for sport, camping and recreation",
    "09.5.1": "Books and stationery (Textbooks, notebooks, pens, copy paper)",
    "10.1.0": "Education services (Tuition fees ONLY - never physical stationery)",
    "11.1.1": "Restaurants, cafes and the like (Dining out, fast food - never supermarkets)",
    "11.2.0": "Accommodation services (Hotels, motels, guesthouses)",
    "12.1.1": "Hairdressing salons and personal grooming establishments",
    "12.1.3": "Personal care products (Toothpaste, soap, cosmetics, skincare, perfumes, diapers)",
    "12.3.1": "Jewellery, clocks and watches",
    "12.3.2": "Other personal effects (Bags, luggage, wallets)",
}

SUPERMARKET_STORES = {"aeon", "aeon3", "delishop", "grab_lucky", "grab_chipmong", "l192"}

PURE_STORE_MAP: dict[str, tuple[str, str]] = {
    "ppwsa": ("04", "04.4.1"),
    "edc": ("04", "04.5.1"),
    "realestate": ("04", "04.1.1"),
    "bookmebus": ("07", "07.3.2"),
    "redbus": ("07", "07.3.2"),
    "redmebus": ("07", "07.3.2"),
    "cellcard": ("08", "08.3.0"),
    "cellcard_wifi": ("08", "08.3.0"),
    "smart": ("08", "08.3.0"),
    "smart_wifi": ("08", "08.3.0"),
    "metfone": ("08", "08.3.0"),
    "sokhahotel": ("11", "11.2.0"),
    "hyyathotel": ("11", "11.2.0"),
    "hyatthotel": ("11", "11.2.0"),
    "hyatt": ("11", "11.2.0"),
    "bayonbkk": ("11", "11.1.1"),
}

VALID_CLASSES_PROMPT = "\n".join(f"- {c}: {desc}" for c, desc in OFFICIAL_CLASSES.items())

SYSTEM_PROMPT = f"""You are an expert economic statistician classifying consumer goods for Cambodia Consumer Price Index (CPI) according to UN COICOP 2018.

You must map each product into EXACTLY ONE of the following valid 5-digit COICOP codes:
{VALID_CLASSES_PROMPT}

MANDATORY CPI RULES:
1. Physical stationery (notebooks, pens, paper, rulers, staplers) MUST be classified as '09.5.1' (Books and stationery), NEVER '10.1.0' (which is strictly tuition fees).
2. Supermarkets (aeon, delishop, l192, grab_lucky, grab_chipmong) CANNOT sell '11.1.1' (restaurants) or '11.2.0' (hotels). Ready meals, sushi, bentos sold in stores are '01.1.1' or '01.1.2'.
3. Culinary vinegars (apple cider vinegar, wine vinegar) and broths/soup bases are '01.1.9' (Seasonings), NOT alcohol or kitchenware.
4. Brand snacks like Bourbon Petit cookies and Camel roasted nuts are '01.1.8' (Confectionery/Snacks), NOT alcohol or tobacco.
5. Baby formula is '01.1.4' (Milk/Dairy). Baby cereals/biscuits are '01.1.1'. Baby purees are '01.1.9'. Diapers/wipes are '12.1.3'.
6. Skincare, shower gels, cleansing oils, and perfumes are '12.1.3' (Personal care), NOT clothing or cooking oil.
7. Phone accessories (phone cases, cooling fans, stands, chargers) are '08.2.0'.
8. Kitchenware (frying pans, pots, knives, water bottles, tableware) are '05.5.1'.
9. Major appliances (fans, irons, rice cookers, kettles) are '05.3.1' -> map to '05.5.1' or '05.1.1'.
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
            "name": it["canonical_name"],
            "stores": it["stores"][:3],
            "categories": it["categories"][:2],
        }
        for it in items_batch
    ]

    prompt = f"""{SYSTEM_PROMPT}

Classify each of the following {len(clean_items)} products.
Input products:
{json.dumps(clean_items, ensure_ascii=False)}

Return a JSON array of objects with keys:
- "id": product id
- "coicop_code": valid 5-digit COICOP code from the list
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
            if err.code in (429, 503, 500):
                if err.code == 429:
                    pool.mark_key_rate_limited(key)
                log.warning("HTTP %d (Attempt %d/%d): %s. Cooling key...", err.code, attempt, MAX_RETRIES, err_body)
                time.sleep(2.0 * attempt)
            else:
                log.error("HTTP %d error: %s", err.code, err_body)
                break
        except Exception as exc:
            log.warning("Request failed (Attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
            time.sleep(2.0 * attempt)

    return []


def validate_and_guard(
    prediction: dict[str, Any],
    item_context: dict[str, Any],
) -> tuple[str, str, float, str]:
    """
    Validates Gemini output and enforces Cambodia CPI domain guardrails.
    Returns (coicop_division, coicop_code, confidence, reasoning).
    """
    code = str(prediction.get("coicop_code", "01.1.9")).strip()
    conf = float(prediction.get("confidence", 0.90))
    reasoning = str(prediction.get("reasoning", "gemini_ai"))
    name_lower = item_context["canonical_name"].lower()
    stores = set(item_context["stores"])

    # Fallback if unknown code returned
    if code not in OFFICIAL_CLASSES:
        div = code[:2]
        if div in ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]:
            matches = [c for c in OFFICIAL_CLASSES if c.startswith(div)]
            code = matches[0] if matches else f"{div}.1.1"
        else:
            code = "01.1.9"

    # Guardrail 1: Physical Stationery in Division 10 -> 09.5.1 (Division 10 is tuition fees only)
    stationery_words = [
        "notebook", "pen", "pencil", "paper", "ruler", "eraser", "stapler",
        "marker", "folder", "binder", "highlighter", "scissors", "glue",
        "calculator", "compass", "envelope", "whiteboard", "sketchbook"
    ]
    if code.startswith("10.") and any(w in name_lower for w in stationery_words):
        code = "09.5.1"
        reasoning = "guardrail_stationery_to_0951"

    # Guardrail 2: Supermarkets cannot sell 11.x (Hospitality) or 04.x (Rentals)
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

    # Guardrail 3: Vinegars / Broths / Seasonings -> 01.1.9
    vinegar_broth_words = [
        "vinegar", "cider vinegar", "wine vinegar", "rice vinegar",
        "broth", "soup base", "bouillon", "dashi", "stock cube",
        "hot pot base", "tom yum paste"
    ]
    if any(w in name_lower for w in vinegar_broth_words) and "cleaning vinegar" not in name_lower:
        if code != "01.1.9":
            code = "01.1.9"
            reasoning = "guardrail_vinegar_broth_to_0119"

    # Guardrail 4: Brand snacks / Camel nuts -> 01.1.8
    if "bourbon petit" in name_lower or ("camel" in name_lower and any(w in name_lower for w in ["nut", "peanut", "cashew", "almond"])):
        if code.startswith("02."):
            code = "01.1.8"
            reasoning = "guardrail_brand_snacks_to_0118"

    # Guardrail 5: Diapers / Baby wipes / Sanitary pads -> 12.1.3
    if any(w in name_lower for w in ["diaper", "drypant", "dry pants", "pampers", "huggies", "baby wipes", "wet wipes", "sanitary pad"]):
        code = "12.1.3"
        reasoning = "guardrail_diapers_to_1213"

    # Guardrail 6: Phone accessories -> 08.2.0
    if any(w in name_lower for w in ["phone case", "cooling fan", "screen protector", "phone holder", "power bank", "charger cable"]):
        code = "08.2.0"
        reasoning = "guardrail_phone_acc_to_0820"

    division = code.split(".")[0]
    return division, code, conf, reasoning


def commit_checkpoint(
    cur,
    conn,
    cache_records: list[tuple[str, str, float, str, str]],
    classified_batch: dict[str, tuple[str, str, float, str]],
) -> None:
    """Commits an incremental batch to silver.dim_coicop_ai_cache and silver.canonical_items."""
    if not cache_records and not classified_batch:
        return

    try:
        if cache_records:
            execute_values(
                cur,
                """
                INSERT INTO silver.dim_coicop_ai_cache
                    (product_name, coicop_code, confidence_score, reasoning, model_version)
                VALUES %s
                ON CONFLICT (product_name) DO UPDATE
                SET coicop_code = EXCLUDED.coicop_code,
                    confidence_score = EXCLUDED.confidence_score,
                    reasoning = EXCLUDED.reasoning,
                    model_version = EXCLUDED.model_version,
                    classified_at = CURRENT_TIMESTAMP;
                """,
                cache_records,
                page_size=2000,
            )

        if classified_batch:
            update_data = [
                (div, code, "gemini_ai", conf, it_id)
                for it_id, (div, code, conf, _) in classified_batch.items()
            ]
            execute_values(
                cur,
                """
                UPDATE silver.canonical_items AS ci
                SET 
                    coicop_division = data.div,
                    coicop_code = data.code,
                    coicop_method = data.method,
                    coicop_confidence = data.conf,
                    coicop_classified_at = CURRENT_TIMESTAMP
                FROM (VALUES %s) AS data(div, code, method, conf, item_id)
                WHERE ci.item_id::text = data.item_id::text;
                """,
                update_data,
                page_size=2000,
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.error("Failed to commit checkpoint: %s", exc)
        raise exc


def run(
    execute: bool = False,
    sample_size: int | None = None,
    limit: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = 4,
    model_name: str = DEFAULT_MODEL,
    resume: bool = False,
):
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    where_filter = "WHERE ci.coicop_method != 'gemini_ai'" if resume else ""

    log.info("Loading catalog items from silver.canonical_items (resume=%s)...", resume)
    cur.execute(f"""
        SELECT 
            ci.item_id::text,
            ci.canonical_name,
            ci.coicop_division,
            ci.coicop_code,
            ci.coicop_method,
            coalesce(array_agg(distinct s.store_slug) filter (where s.store_slug is not null), '{{}}') as stores,
            coalesce(array_agg(distinct s.category_native) filter (where s.category_native is not null and s.category_native <> ''), '{{}}') as categories
        FROM silver.canonical_items ci
        LEFT JOIN silver.clean_store_prices s ON ci.item_id::text = s.item_id::text
        {where_filter}
        GROUP BY ci.item_id, ci.canonical_name, ci.coicop_division, ci.coicop_code, ci.coicop_method;
    """)
    all_rows = cur.fetchall()
    log.info("Total candidate items loaded: %d", len(all_rows))

    # Separate items that have 100% store domain purity (no AI query needed)
    items_to_classify = []
    pure_store_items = 0

    for r in all_rows:
        item_id, name, cur_div, cur_code, cur_method, stores, categories = r
        stores_set = {s.lower().strip() for s in stores if s}
        
        # Pure store bypass
        if stores_set and stores_set.issubset(set(PURE_STORE_MAP.keys())):
            pure_store_items += 1
            continue

        items_to_classify.append({
            "item_id": item_id,
            "canonical_name": name,
            "cur_div": cur_div,
            "cur_code": cur_code,
            "cur_method": cur_method,
            "stores": stores,
            "categories": categories,
        })

    log.info("Store domain pure items (bypassed): %d", pure_store_items)
    log.info("Candidate items for Gemini AI classification: %d", len(items_to_classify))

    if sample_size and sample_size > 0:
        items_to_classify = items_to_classify[:sample_size]
        log.info("Sampling active: limited to %d items.", len(items_to_classify))
    elif limit and limit > 0:
        items_to_classify = items_to_classify[:limit]
        log.info("Limit active: limited to %d items.", len(items_to_classify))

    pool = GeminiKeyPool()
    if pool.get_key_count() == 0:
        log.error("No Gemini API keys found. Exiting.")
        return

    workers = min(max_workers, pool.get_key_count())
    batches = [items_to_classify[i:i + batch_size] for i in range(0, len(items_to_classify), batch_size)]
    log.info("Formed %d batches of up to %d items. Dispatching across %d workers with model '%s'...",
             len(batches), batch_size, workers, model_name)

    items_by_id = {it["item_id"]: it for it in items_to_classify}
    classified_results: dict[str, tuple[str, str, float, str]] = {}
    pending_ai_cache: list[tuple[str, str, float, str, str]] = []
    pending_classified: dict[str, tuple[str, str, float, str]] = {}

    start_time = time.time()
    completed_batches = 0
    checkpoint_interval = 10  # Commit every 10 batches (~500 items)

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
                        div, code, conf, reasoning = validate_and_guard(p, it)
                    else:
                        # Fallback to current baseline if batch prediction missed item
                        div = it["cur_div"] or "01"
                        code = it["cur_code"] or "01.1.9"
                        conf = 0.85
                        reasoning = "baseline_preserved"

                    res = (div, code, conf, reasoning)
                    classified_results[item_id] = res
                    pending_classified[item_id] = res
                    pending_ai_cache.append((
                        it["canonical_name"],
                        code,
                        conf,
                        reasoning,
                        model_name,
                    ))

                # Checkpoint commit every 10 batches in execute mode
                if execute and completed_batches % checkpoint_interval == 0:
                    commit_checkpoint(cur, conn, pending_ai_cache, pending_classified)
                    log.info("Checkpoint: committed %d items to canonical_items & ai_cache.", len(pending_classified))
                    pending_ai_cache.clear()
                    pending_classified.clear()

                if completed_batches % 5 == 0 or completed_batches == len(batches):
                    elapsed = time.time() - start_time
                    items_done = len(classified_results)
                    rate = items_done / elapsed if elapsed > 0 else 0
                    log.info("Progress: %d/%d batches (%d items, %.1f items/s)",
                             completed_batches, len(batches), items_done, rate)

            except Exception as exc:
                log.error("Batch error: %s", exc)

    # Commit any remaining pending records in execute mode
    if execute and (pending_ai_cache or pending_classified):
        commit_checkpoint(cur, conn, pending_ai_cache, pending_classified)
        pending_ai_cache.clear()
        pending_classified.clear()

    log.info("Gemini AI classification phase complete in %.1fs.", time.time() - start_time)
    log.info("Total items classified: %d", len(classified_results))

    # Summary of changes
    div_changes = sum(
        1 for it_id, (div, _, _, _) in classified_results.items()
        if div != items_by_id[it_id]["cur_div"]
    )
    code_changes = sum(
        1 for it_id, (_, code, _, _) in classified_results.items()
        if code != items_by_id[it_id]["cur_code"]
    )

    log.info("Proposed 5-digit code changes: %d (%.2f%%)", code_changes, 100.0 * code_changes / len(classified_results) if classified_results else 0)
    log.info("Proposed division changes: %d (%.2f%%)", div_changes, 100.0 * div_changes / len(classified_results) if classified_results else 0)

    # Sample diff preview
    diffs = [
        (items_by_id[it_id]["canonical_name"], items_by_id[it_id]["cur_code"], code,
         items_by_id[it_id]["cur_div"], div, conf, rsn)
        for it_id, (div, code, conf, rsn) in classified_results.items()
        if code != items_by_id[it_id]["cur_code"]
    ]
    if diffs:
        log.info("--- SAMPLE RECLASSIFICATIONS (%d changed items) ---", len(diffs))
        for name, old_c, new_c, old_d, new_d, conf, rsn in diffs[:15]:
            log.info("  * %s: %s -> %s (Div %s->%s, conf=%.2f, reason=%s)",
                     name[:45], old_c, new_c, old_d, new_d, conf, rsn)

    if not execute:
        log.info("DRY RUN completed. Run with --execute to commit to PostgreSQL.")
        conn.close()
        return

    log.info("SYNCHRONIZING DOWNSTREAM TABLES...")
    # Synchronize gold.dim_items
    log.info("Synchronizing gold.dim_items...")
    cur.execute("""
        UPDATE gold.dim_items di
        SET 
            coicop_division = ci.coicop_division,
            coicop_code = ci.coicop_code
        FROM silver.canonical_items ci
        WHERE di.item_id::text = ci.item_id::text
          AND (di.coicop_division IS DISTINCT FROM ci.coicop_division OR
               di.coicop_code IS DISTINCT FROM ci.coicop_code);
    """)
    synced_dim = cur.rowcount
    conn.commit()
    log.info("Synchronized %d items in gold.dim_items.", synced_dim)

    # Synchronize silver.clean_store_prices across all historical dates
    log.info("Synchronizing silver.clean_store_prices across all dates...")
    cur.execute("""
        UPDATE silver.clean_store_prices s
        SET 
            coicop_division = ci.coicop_division,
            coicop_code = ci.coicop_code,
            coicop_method = ci.coicop_method,
            coicop_confidence = ci.coicop_confidence
        FROM silver.canonical_items ci
        WHERE s.item_id::text = ci.item_id::text
          AND (
              s.coicop_division IS DISTINCT FROM ci.coicop_division OR
              s.coicop_code IS DISTINCT FROM ci.coicop_code OR
              s.coicop_method IS DISTINCT FROM ci.coicop_method
          );
    """)
    synced_prices = cur.rowcount
    conn.commit()
    log.info("Synchronized %d observations in silver.clean_store_prices.", synced_prices)

    log.info("ALL DATABASE COMMITS COMPLETED SUCCESSFULLY!")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="One-time Gemini AI COICOP Catalog Classifier")
    parser.add_argument("--execute", action="store_true", help="Commit changes to PostgreSQL")
    parser.add_argument("--resume", action="store_true", help="Only classify items not yet classified by gemini_ai")
    parser.add_argument("--sample", type=int, default=None, help="Sample N items to test")
    parser.add_argument("--limit", type=int, default=None, help="Limit to N items")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size per API call")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Gemini model name")
    args = parser.parse_args()

    run(
        execute=args.execute,
        sample_size=args.sample,
        limit=args.limit,
        batch_size=args.batch_size,
        max_workers=args.workers,
        model_name=args.model,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
