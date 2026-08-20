"""
pipeline/gemini_coicop_classifier.py
────────────────────────────────────
Gemini AI COICOP 2018 classifier for Silver-layer products (Prompt 5).

Classifies the products that the rule-based dbt rules and the local ML model
left at the '99.9.9' placeholder. Runs as an Airflow PythonOperator.

Pipeline:
    1. Read still-unclassified product names from silver.dim_canonical_products.
    2. Consult silver.dim_coicop_ai_cache first — a cached product name never
       triggers an API call (memoization saves API cost on re-scrapes).
    3. Batch the uncached names in chunks of ``BATCH_SIZE`` (50) and send each
       batch to Google Gemini in JSON mode (``response_mime_type='application/json'``)
       so the model is forced to return a machine-parseable JSON array.
    4. Persist the fresh results into the cache and write ``coicop_code``,
       ``classification_method = 'gemini_ai'`` and ``confidence_score`` back into
       staging.stg_item_mapping (and keep silver.dim_canonical_products in sync,
       which is what the dbt fact models join on).

The system prompt is intentionally detailed: it pins the model to the UN COICOP
2018 taxonomy, the 5-digit dotted notation, the '99.9.9' fallback, and a strict
JSON contract with product_name / coicop_code / confidence_score / reasoning.

Requires: google-generativeai, sqlalchemy.  API key via GEMINI_API_KEY,
model name via GEMINI_MODEL (default gemini-3.1-flash-lite).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from sqlalchemy import create_engine, text

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - only present in the Airflow image
    genai = None

log = logging.getLogger(__name__)

BATCH_SIZE = 50  # Gemini batch size
DEFAULT_MODEL = "gemini-3.1-flash-lite"
UNCLASSIFIED = "99.9.9"
CLASSIFICATION_METHOD = "gemini_ai"

SYSTEM_PROMPT = """You are an expert statistical classifier for the UN COICOP 2018 taxonomy (Classification of Individual Consumption According to Purpose). I will give you a list of e-commerce product names from Cambodia. You must return a JSON array mapping each product to its most specific 5-digit COICOP code. If unsure, return '99.9.9'. Include a 'confidence_score' (0.0 to 1.0) and a brief 'reasoning' string.

Classification rules:
- Use the official dotted 5-digit COICOP 2018 notation, e.g. '01.1.1' (Bread and cereals) or '07.2.2' (Fuels and lubricants for personal transport equipment).
- Prefer the MOST SPECIFIC code the name unambiguously supports. Never invent a finer class than the name justifies.
- If the product cannot be confidently mapped to any COICOP class, return the special code '99.9.9'.
- Classify only what the name literally describes. Do not infer bundles, promotions or brand-only categories unless the name says so.
- 'product_name' in the response MUST exactly match the input name so results can be joined back.
- 'confidence_score' must be a float from 0.0 to 1.0.
- 'reasoning' must be a short (max 15 words) English explanation.

Common COICOP 2018 codes you will need:
- 01.1.1 Bread and cereals (rice, flour, pasta, cereal, noodles, bread, buns, rolls, croissants)
- 01.1.2 Meat (fresh meat, frozen meat, sausages, bacon, ham, jerky, dried meat)
- 01.1.3 Fish and seafood (fresh fish, frozen fish, shrimp, squid, dried fish, dried shrimp, fish sauce, oyster sauce)
- 01.1.4 Milk, cheese and eggs (milk, yogurt, cheese, eggs, butter, condensed milk, powdered milk, baby formula)
- 01.1.5 Oils and fats (cooking oil, olive oil, coconut oil, sesame oil, butter, margarine, ghee)
- 01.1.6 Fruit (fresh fruit, dried fruit, frozen fruit, fruit juice, fruit smoothie)
- 01.1.7 Vegetables (fresh vegetables, frozen vegetables, canned vegetables, salad, herbs, spices, seasonings, sauces, condiments, pickles)
- 01.1.8 Sugar, jam, honey, chocolate and confectionery (sugar, honey, jam, chocolate, candy, lollipop, gummy, marshmallow, cookies, biscuits, wafers, cakes, pastries)
- 01.2.1 Coffee, tea and cocoa (coffee, tea, cocoa, hot chocolate, instant coffee, coffee beans, tea bags)
- 01.2.2 Mineral waters, soft drinks, juices (water, soda, juice, energy drink, sports drink, coconut water, aloe vera drink)
- 02.1.1 Spirits (whiskey, vodka, rum, gin, tequila, brandy, soju, baijiu)
- 02.1.2 Wine (red wine, white wine, rose, champagne, sparkling wine)
- 02.2.1 Beer (beer, lager, stout, pilsner, ale, draft beer, craft beer)
- 02.2.0 Tobacco (cigarettes, cigars, tobacco, chewing tobacco, snus)
- 03.1.1 Garments for men (men shirt, men t-shirt, men pants, men jacket, men coat, men shorts, men suit, men hoodie)
- 03.1.2 Garments for women (women dress, women blouse, women skirt, women jacket, women coat, women pants, women shorts)
- 03.1.3 Garments for infants (baby clothes, baby onesie, baby bodysuit, baby pajamas)
- 03.1.4 Other garments (unisex clothing, uniform, apron, raincoat, swimwear, underwear, socks)
- 03.2.1 Shoes and other footwear (shoes, sneakers, boots, sandals, flip-flops, slippers, heels, loafers, crocs)
- 04.1.1 Actual rentals for housing (rent, rental, apartment rent, condo rent, house rent)
- 04.2.1 Imputed rentals for housing (not directly applicable to purchases)
- 04.3.1 Maintenance and repair of the dwelling (plumber, electrician, renovation, repair, painting, pest control)
- 04.4.1 Water supply and related services (water bill, water rate, water meter)
- 04.5.1 Electricity (electric bill, power bill, electricity meter, kwh)
- 04.5.2 Gas (gas cylinder, gas tank, lpg, gas bill)
- 04.5.3 Liquid fuels (kerosene, firewood, charcoal for cooking)
- 05.1.1 Furniture and furnishings (sofa, chair, table, bed, desk, wardrobe, shelf, bookcase, dresser)
- 05.2.1 Household textiles (towel, curtains, bedsheet, pillow, blanket, linen, tablecloth)
- 05.3.1 Major household appliances (refrigerator, fridge, freezer, washing machine, dryer, dishwasher, oven, microwave, air conditioner, fan, water heater)
- 05.4.1 Small electric household appliances (kettle, blender, toaster, vacuum, iron, rice cooker, coffee maker, air fryer, food processor, mixer, juicer, slow cooker, pressure cooker, hair dryer)
- 05.5.1 Glassware, tableware and household utensils (plate, bowl, cup, mug, glass, cutlery, fork, spoon, knife, pan, pot, wok, baking tray)
- 05.6.1 Non-durable household goods (detergent, soap, bleach, dish soap, cleaning product, sponge, trash bag, toilet paper, paper towel, tissue)
- 06.1.1 Medical and paramedical services (doctor visit, clinic, hospital, dental, physiotherapy)
- 06.1.2 Pharmaceutical products (medicine, paracetamol, ibuprofen, panadol, aspirin, antibiotic, cough syrup, inhaler, ointment, bandage, first aid kit)
- 06.1.3 Other medical products (thermometer, blood pressure monitor, glucose meter, pregnancy test, contact lens solution, condoms, surgical gloves)
- 06.1.4 Therapeutic medical appliances (crutches, wheelchair, hearing aid, oxygen tank)
- 06.2.1 Dental services (dental cleaning, dental filling, dental extraction, dental whitening, braces)
- 06.3.1 Spectacles and lenses (prescription glasses, corrective contact lenses)
- 07.1.1 Passenger transport by railway (train ticket, rail fare)
- 07.1.2 Passenger transport by road (bus ticket, express bus, passenger van)
- 07.1.3 Passenger transport by air (airline ticket, airfare, flight)
- 07.1.4 Passenger transport by water (ferry ticket, boat fare)
- 07.2.1 Spare parts and accessories for personal transport equipment (car parts, brake pads, spark plug, oil filter, car battery, tire)
- 07.2.2 Fuels and lubricants for personal transport equipment (gasoline, petrol, diesel, engine oil, motor oil)
- 07.2.3 Maintenance and repair of personal transport equipment (car wash, car service, oil change)
- 08.1.1 Postal services (postage stamp, courier, delivery fee, parcel)
- 08.2.0 Telephone and telefax equipment (smartphone, mobile phone, telephone, tablet, iPad, phone charger, charging cable, phone case)
- 08.3.0 Telephone and telefax services / Internet services (internet plan, broadband, fiber, wifi, data plan, mobile data, SIM card, airtime, top-up, mobile plan)
- 09.1.1 Audio-visual equipment (TV, camera, headphone, speaker, soundbar, projector)
- 09.1.2 Photographic and cinematographic equipment (DSLR camera, action camera, GoPro, tripod, lens, memory card)
- 09.1.3 Information processing equipment (personal computer, laptop, Macbook, printer)
- 09.1.4 Recording media (CD, DVD, USB drive, SD card)
- 09.2.2 Musical instruments (guitar, piano, violin, drums, keyboard)
- 09.3.1 Games, toys and hobbies (toy, doll, Barbie, Hot Wheels, puzzle, board game, video game, Lego, action figure)
- 09.3.2 Equipment for sport, camping and open-air recreation (football, basketball, tennis, badminton, bicycle, camping tent)
- 09.3.3 Gardens, plants and flowers (natural or artificial plants, flowers, seeds, fertilizers, pots)
- 09.3.4 Pets and related products (pet food, dog food, cat food, kitten food, puppy food, pet treats, cat litter, pet toys, pet shampoo, pet accessories)
- 09.5.1 Books (book, novel, textbook, dictionary, atlas, guide book)
- 09.5.2 Newspapers and periodicals (newspaper, magazine, journal)
- 09.5.4 Stationery and drawing materials (pen, pencil, ruler, eraser, sharpener, notebook, exercise book, crayon, marker, highlighter, stapler, envelope, paper, folder, binder, scissors, glue)
- 10.1.0 Pre-primary and primary education services (kindergarten, primary school, elementary school tuition)
- 10.2.0 Secondary education services (secondary school, high school tuition)
- 10.4.0 Tertiary education services (university, college tuition, degree courses)
- 10.5.0 Education not definable by level (vocational training, language course tuition)
- 11.1.1 Restaurants and cafes (restaurant, cafe, diner, bistro, cafeteria, fast food, meal, dining)
- 11.2.0 Accommodation services (hotel room, resort stay, guesthouse, Airbnb, serviced apartment)
- 12.1.1 Hairdressing and personal grooming (haircut, hair salon, beauty salon, nail salon, manicure, pedicure, facial treatment, spa, massage)
- 12.1.2 Appliances and products for personal hygiene (hair dryer, electric shaver, razor, dental floss, mouthwash)
- 12.1.3 Articles and products for personal care (shampoo, conditioner, soap, body wash, lotion, moisturizer, sunscreen, skincare, face cream, makeup, lipstick, perfume, cologne, baby lotion, baby powder)
- 12.2.0 Jewellery, watches and luggage (necklace, earring, ring, bracelet, analog watch, quartz watch, handbag, suitcase, wallet, purse, sunglasses, umbrella)
- 12.2.1 Postal and courier services (same as 08.1.1)
- 12.2.2 Financial services (bank fee, insurance premium, investment, loan, mortgage, interest)
- 12.3.1 Housing maintenance and repair services (plumber, electrician, renovation, painting, pest control, gardening, landscaping)
- 12.4.0 Other services not elsewhere classified (legal service, accounting, consulting, photography, printing, laundry, dry cleaning, tailoring, repair, storage)
- 12.5.1 Social protection services (social security, welfare, pension, unemployment benefits)
- 12.6.0 Other services (charity, donation, subscription, membership, licensing, certification, inspection)

Cambodian market examples:
- "Jasmine Rice 5kg" -> 01.1.1 (Bread and cereals)
- "Angkor Beer Can 330ml" -> 02.2.1 (Beer)
- "Pedigree Dog Food Beef 1.5kg" -> 09.3.4 (Pets and related products)
- "Whiskas Cat Food Tuna 1.2kg" -> 09.3.4 (Pets and related products)
- "Paracetamol 500mg 100 Tablets" -> 06.1.2 (Pharmaceutical products)
- "Samsung Galaxy A15 128GB" -> 08.2.0 (Telephone equipment)
- "Home Fiber 50 Mbps Monthly" -> 08.3.0 (Internet services)
- "Deluxe Room River View (1 Night)" -> 11.2.0 (Accommodation services)
- "Pork Fried Rice (Bai Cha)" -> 11.1.1 (Restaurants and cafes)
- "Bus Ticket Phnom Penh - Siem Reap" -> 07.1.2 (Passenger transport by road)
- "1 Bedroom Condo BKK1 Rent" -> 04.1.1 (Actual rentals for housing)
- "Exercise Book A4 120 Pages" -> 09.1.2 (Stationery)
- "Electric Kettle 1.8L" -> 05.4.1 (Small electric household appliances)
- "Regular Gasoline" -> 07.2.2 (Fuels and lubricants)
- "USD/KHR Exchange Rate" -> 99.9.9 (Not a consumer good)
- "Smart Laor! 8GB Weekly" -> 08.4.0 (Other communication services)
- "Smart Fiber+ 80 Mbps" -> 08.3.0 (Internet services)
- "BIC Ball Pen Blue" -> 09.1.2 (Stationery)
- "Crayola Crayons 24 Colors" -> 09.1.2 (Stationery)
- "Fresh Milk 1L Pasteurised" -> 01.1.4 (Milk, cheese and eggs)
- "Eggs Tray 10s" -> 01.1.4 (Milk, cheese and eggs)
- "Avocado Hass Fresh 500g" -> 01.1.6 (Fruit)
- "Non-Stick Frying Pan 28cm" -> 05.5.1 (Glassware, tableware and household utensils)
- "Men Cotton T-Shirt" -> 03.1.1 (Garments for men)
- "Women Running Shoes" -> 03.2.1 (Shoes and other footwear)
- "Apple USB-C Fast Charger 20W" -> 08.2.0 (Telephone equipment)
- "Executive Suite 1 Night" -> 11.2.0 (Accommodation services)
- "Iced Milk Coffee (Kafe Teuk Doh Koh)" -> 11.1.1 (Restaurants and cafes)
- "Express Van Phnom Penh - Battambang" -> 07.1.2 (Passenger transport by road)
- "VIP Van Phnom Penh - Sihanoukville" -> 07.1.2 (Passenger transport by road)
- "Standard King Room 1 Night" -> 11.2.0 (Accommodation services)

Response format (strict JSON array, no markdown fences, no extra text):
[{"product_name": "<exact input name>", "coicop_code": "01.1.4", "confidence_score": 0.95, "reasoning": "Unambiguous whole milk product"}]
"""


def get_engine():
    conn_str = os.getenv(
        "CPI_DATABASE_URL",
        "postgresql+psycopg2://cpi_user:cpi_pass@postgres:5432/cpi_db",
    )
    return create_engine(conn_str)


def _normalize_name(name: str) -> str:
    """Cache key for a product name: case-folded and whitespace-normalized."""
    return re.sub(r"\s+", " ", str(name)).strip().lower()


def _build_model():
    if genai is None:
        raise RuntimeError(
            "google-generativeai is required (pip install google-generativeai)"
        )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set; Gemini COICOP classification cannot run"
        )
    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    log.info("Building Gemini model %s with JSON mode", model_name)
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=genai.GenerationConfig(response_mime_type="application/json"),
    )


def _parse_json_array(raw_text: str) -> list[dict[str, Any]]:
    """Robustly parses a JSON array from a model response (strips markdown fences)."""
    text_clean = raw_text.strip()
    if text_clean.startswith("```"):
        text_clean = re.sub(r"^```(?:json)?\s*", "", text_clean)
        text_clean = re.sub(r"\s*```$", "", text_clean)
    try:
        parsed = json.loads(text_clean)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text_clean)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}")
    return parsed


def classify_batch(model, names: list[str]) -> list[dict[str, Any]]:
    """
    Sends one batch of product names to Gemini in JSON mode and parses the
    returned array. Raises on an unparseable or incomplete response so the
    caller can mark the batch as failed.
    """
    response = model.generate_content(names, system_instruction=SYSTEM_PROMPT)
    results = _parse_json_array(response.text)

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "product_name": str(item.get("product_name") or "").strip(),
                "coicop_code": str(item.get("coicop_code") or UNCLASSIFIED).strip(),
                "confidence_score": float(item.get("confidence_score") or 0.0),
                "reasoning": str(item.get("reasoning") or ""),
            }
        )
    return normalized


def classify_names(
    names: list[str],
    model=None,
    cache: dict[str, dict[str, Any]] | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, Any]:
    """
    Classifies product names using Gemini with per-name memoization.

    ``cache`` maps normalized product name -> cached result dict. Names with a
    cache hit never reach the API. Returns:
        {"results": {name: result}, "cache_hits": int, "api_calls": int, "failed": int}
    """
    if model is None:
        model = _build_model()

    cache = cache or {}
    seen: dict[str, dict[str, Any]] = {}

    # 1. Resolve every name: cache first, API second (in batches of 50).
    names = [str(n) for n in names]
    api_batches: list[list[str]] = []
    batch: list[str] = []
    for name in names:
        key = _normalize_name(name)
        if key in cache:
            seen[name] = dict(cache[key])
            continue
        batch.append(name)
        if len(batch) == batch_size:
            api_batches.append(batch)
            batch = []
    if batch:
        api_batches.append(batch)

    cache_hits = len(seen)
    api_calls = 0
    failed = 0
    for batch in api_batches:
        api_calls += 1
        try:
            for item in classify_batch(model, batch):
                item_name = item["product_name"]
                if not item_name:
                    continue
                key = _normalize_name(item_name)
                cache[key] = item
                # prefer the exact input spelling for the join back to the row
                seen[item_name] = item
        except Exception as exc:  # noqa: BLE001 - one bad batch must not kill the run
            failed += 1
            log.warning("Gemini batch of %d name(s) failed: %s", len(batch), exc)
            # Re-check: any name in the failed batch that is still uncached stays
            # unclassified (classified later once the API is healthy again).
            for name in batch:
                seen.setdefault(name, _unclassified_result(name))

    return {"results": seen, "cache_hits": cache_hits, "api_calls": api_calls, "failed": failed}


def _unclassified_result(name: str) -> dict[str, Any]:
    return {
        "product_name": name,
        "coicop_code": UNCLASSIFIED,
        "confidence_score": 0.0,
        "reasoning": "Gemini call failed; left unclassified",
    }


def fetch_unclassified(engine, table_name: str | None = None) -> list[dict[str, Any]]:
    """Returns active unclassified products from classification_queue or dim_canonical_products."""
    items: list[dict[str, Any]] = []
    with engine.connect() as conn:
        try:
            # First check silver.classification_queue
            q_res = conn.execute(
                text(
                    "SELECT product_key as canonical_item_id, name_clean as canonical_name "
                    "FROM silver.classification_queue "
                    "WHERE status = 'PENDING'"
                )
            ).fetchall()
            for r in q_res:
                items.append({"canonical_item_id": str(r[0]), "canonical_name": str(r[1])})
        except Exception:
            pass

        if not items:
            try:
                # Check silver.dim_canonical_products
                dim_res = conn.execute(
                    text(
                        "SELECT canonical_item_id, canonical_name FROM silver.dim_canonical_products "
                        "WHERE (coicop_code = '99.9.9' OR coicop_code IS NULL)"
                    )
                ).fetchall()
                for r in dim_res:
                    items.append({"canonical_item_id": str(r[0]), "canonical_name": str(r[1])})
            except Exception:
                pass

    return items


def load_cache(engine) -> dict[str, dict[str, Any]]:
    """Loads the whole Gemini cache & verified Ground Truth labels keyed by normalized product name."""
    cache = {}
    with engine.connect() as conn:
        # 1. Load AI Cache
        try:
            query = text(
                "SELECT product_name, coicop_code, confidence_score, reasoning "
                "FROM silver.dim_coicop_ai_cache"
            )
            rows = conn.execute(query).fetchall()
            for name, coicop, confidence, reasoning in rows:
                cache[_normalize_name(name)] = {
                    "product_name": str(name),
                    "coicop_code": str(coicop),
                    "confidence_score": float(confidence or 0.0),
                    "reasoning": str(reasoning or ""),
                }
        except Exception as e:
            log.warning("Could not read dim_coicop_ai_cache: %s", e)

        # 2. Load Ground Truth (Highest Priority, Overwrites AI Cache)
        try:
            gt_query = text(
                "SELECT product_name, coicop_code, confidence_score, notes "
                "FROM silver.classification_ground_truth"
            )
            gt_rows = conn.execute(gt_query).fetchall()
            for name, coicop, confidence, notes in gt_rows:
                cache[_normalize_name(name)] = {
                    "product_name": str(name),
                    "coicop_code": str(coicop),
                    "confidence_score": float(confidence or 1.0),
                    "reasoning": f"Ground Truth: {notes or 'human verified'}",
                }
        except Exception as e:
            log.info("Ground truth table not yet populated or accessible: %s", e)

    log.info("Loaded %d cached and ground-truth COICOP classifications", len(cache))
    return cache


def update_cache(engine, results: dict[str, dict[str, Any]]) -> int:
    """
    Upserts fresh Gemini results into silver.dim_coicop_ai_cache.

    '99.9.9' (unclassified) outcomes are deliberately NOT cached so a product
    can be re-attempted on a later run once the model improves or more context
    exists.
    """
    rows = [
        r
        for r in results.values()
        if r.get("confidence_score", 0.0) > 0.0 and r.get("coicop_code") != UNCLASSIFIED
    ]
    if not rows:
        return 0
    stmt = text(
        """
        INSERT INTO silver.dim_coicop_ai_cache
            (product_name, coicop_code, confidence_score, reasoning, model_version)
        VALUES (:name, :coicop, :confidence, :reasoning, :model)
        ON CONFLICT (product_name) DO UPDATE
        SET coicop_code = EXCLUDED.coicop_code,
            confidence_score = EXCLUDED.confidence_score,
            reasoning = EXCLUDED.reasoning,
            model_version = EXCLUDED.model_version,
            classified_at = CURRENT_TIMESTAMP
        """
    )
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    n = 0
    with engine.begin() as conn:
        for row in rows:
            conn.execute(
                stmt,
                {
                    "name": row["product_name"],
                    "coicop": row["coicop_code"],
                    "confidence": round(row["confidence_score"], 4),
                    "reasoning": row["reasoning"],
                    "model": model,
                },
            )
            n += 1
    log.info("Upserted %d row(s) into dim_coicop_ai_cache", n)
    return n


def persist_classifications(
    engine,
    results: dict[str, dict[str, Any]],
    items: list[dict[str, Any]],
    scrape_date: str | None = None,
) -> int:
    """
    Writes coicop_code / classification_method='gemini_ai' / confidence_score
    back into silver.classification_queue and silver.dim_canonical_products.
    """
    by_name = {_normalize_name(i["canonical_name"]): i["canonical_item_id"] for i in items}
    updates = []
    for name, result in results.items():
        cid = by_name.get(_normalize_name(name))
        if cid is None or result["coicop_code"] == UNCLASSIFIED:
            continue
        updates.append(
            {
                "canonical_item_id": cid,
                "coicop_code": result["coicop_code"],
                "confidence_score": round(result["confidence_score"], 4),
            }
        )
    if not updates:
        return 0

    update_queue_resolved_sql = text(
        """
        UPDATE silver.classification_queue
        SET status = 'RESOLVED',
            resolved_division = :division,
            resolved_at = CURRENT_TIMESTAMP
        WHERE product_key = :canonical_item_id
        """
    )
    update_queue_pending_sql = text(
        """
        UPDATE silver.classification_queue
        SET status = 'PENDING',
            reason = 'low confidence AI classification'
        WHERE product_key = :canonical_item_id
        """
    )
    update_dim_sql = text(
        """
        UPDATE silver.dim_canonical_products
        SET coicop_code = :coicop_code,
            classification_method = :method,
            confidence_score = :confidence_score,
            needs_review = :needs_review
        WHERE canonical_item_id = :canonical_item_id
        """
    )

    update_mapping_sql = text(
        """
        UPDATE staging.stg_item_mapping
        SET coicop_code = :coicop_code,
            classification_method = :method,
            confidence_score = :confidence_score
        WHERE canonical_item_id = :canonical_item_id
          AND (coicop_code IS NULL OR coicop_code = '99.9.9')
        """
    )

    n_queue = 0
    n_dim = 0
    n_mapping = 0
    with engine.begin() as conn:
        for row in updates:
            conf = row["confidence_score"]
            is_low_conf = conf < 0.50
            method = "gemini_ai_low_conf" if is_low_conf else "gemini_ai"
            division = row["coicop_code"].split(".")[0].zfill(2)
            params = {
                "canonical_item_id": row["canonical_item_id"],
                "coicop_code": row["coicop_code"],
                "confidence_score": conf,
                "method": method,
                "division": division,
                "needs_review": is_low_conf,
            }
            try:
                if is_low_conf:
                    res_q = conn.execute(update_queue_pending_sql, {"canonical_item_id": row["canonical_item_id"]})
                else:
                    res_q = conn.execute(update_queue_resolved_sql, {"canonical_item_id": row["canonical_item_id"], "division": division})
                n_queue += res_q.rowcount or 0
            except Exception:
                pass
            try:
                res_d = conn.execute(update_dim_sql, params)
                n_dim += res_d.rowcount or 0
            except Exception:
                pass
            try:
                if scrape_date:
                    mapping = update_mapping_sql.text + " AND scrape_date = :scrape_date"
                    res_m = conn.execute(
                        text(mapping),
                        {**params, "scrape_date": scrape_date},
                    )
                else:
                    res_m = conn.execute(update_mapping_sql, params)
                n_mapping += res_m.rowcount or 0
            except Exception:
                pass
    log.info(
        "Persisted Gemini COICOP codes: %d queue item(s) resolved, %d dimension row(s), %d mapping row(s)",
        n_queue,
        n_dim,
        n_mapping,
    )
    return n_mapping or n_queue or n_dim


def classify_unclassified_with_gemini(
    engine=None,
    scrape_date: str | None = None,
    batch_size: int = BATCH_SIZE,
    model=None,
) -> dict[str, Any]:
    """
    Gemini AI COICOP classification entry point (Airflow PythonOperator callable).

    Classifies every product still at '99.9.9', using the cache first, then
    Gemini JSON mode in batches of 50, and persists the results.
    """
    engine = engine or get_engine()
    items = fetch_unclassified(engine)
    if not items:
        log.info("No unclassified products to classify with Gemini")
        return {"status": "SKIPPED_NO_UNCLASSIFIED", "candidates": 0, "classified": 0}

    cache = load_cache(engine)
    names = [i["canonical_name"] for i in items]
    outcome = classify_names(names, model=model, cache=cache, batch_size=batch_size)

    update_cache(engine, outcome["results"])
    n_mapping = persist_classifications(engine, outcome["results"], items, scrape_date)

    classified = sum(1 for r in outcome["results"].values() if r["coicop_code"] != UNCLASSIFIED)
    return {
        "status": "OK",
        "candidates": len(items),
        "classified": classified,
        "cache_hits": outcome["cache_hits"],
        "api_calls": outcome["api_calls"],
        "failed_batches": outcome["failed"],
        "mapping_rows_updated": n_mapping,
    }
