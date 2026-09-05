"""
pipeline/gemini_coicop_classifier.py
────────────────────────────────────
Gemini AI COICOP 2018 classifier for Silver-layer products (Prompt 5).

Classifies the products that the rule-based dbt rules and the local ML model
left at the '99.9.9' placeholder. Runs as an Airflow PythonOperator.

Pipeline:
    1. Read still-unclassified product names from silver.classification_queue
       (the triage queue populated by int_coicop_classified.sql whenever a row
       falls through every rule tier), with an AI-first fallback that joins
       silver.int_prices_cleaned against silver.canonical_items to surface any
       cached-miss product name from the current scrape.
    2. Consult silver.dim_coicop_ai_cache first — a cached product name never
       triggers an API call (memoization saves API cost on re-scrapes).
    3. Batch the uncached names in chunks of ``BATCH_SIZE`` (50) and send each
       batch to Google Gemini in JSON mode (``response_mime_type='application/json'``)
       so the model is forced to return a machine-parseable JSON array.
    4. Persist the fresh results into silver.dim_coicop_ai_cache (the single
       source of truth read by dbt/models/silver/intermediate/int_coicop_classified.sql
       tier 3) and mark the originating silver.classification_queue rows as
       RESOLVED.

NOTE — single source of truth:
    silver.dim_coicop_ai_cache is the ONLY Gemini write target. Earlier versions
    of this module also wrote back to silver.dim_canonical_products, but that
    table is not joined by any dbt model that propagates COICOP into the
    Silver/Gold facts, so those writes were silently lost. The dbt ladder
    (int_coicop_classified.sql) is the only authoritative classifier — Gemini
    only populates the cache, which the ladder consults as tier 3.

The system prompt is intentionally detailed: it pins the model to the UN COICOP
2018 taxonomy, the 5-digit dotted notation, the '99.9.9' fallback, and a strict
JSON contract with product_name / coicop_code / confidence_score / reasoning.

Requires: google-generativeai, sqlalchemy.  API key via GEMINI_API_KEY,
model name via GEMINI_MODEL (default gemini-2.5-flash).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from sqlalchemy import create_engine, text

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - only present in the Airflow image
    genai = None

log = logging.getLogger(__name__)

BATCH_SIZE = int(os.getenv("GEMINI_BATCH_SIZE", "200"))  # Gemini batch size (was 50)
DEFAULT_MODEL = "gemini-2.5-flash"
UNCLASSIFIED = "99.9.9"
CLASSIFICATION_METHOD = "gemini_ai"

# Rate-limit safety: pause between API batches, and back off + retry once
# when Google answers 429 / ResourceExhausted.
BATCH_DELAY_SECONDS = float(os.getenv("GEMINI_BATCH_DELAY_SECONDS", "2"))
RATE_LIMIT_BACKOFF_SECONDS = float(os.getenv("GEMINI_429_BACKOFF_SECONDS", "30"))

# Phase 2: Adaptive rate limiting — exponential backoff instead of hard circuit breaker.
INITIAL_BACKOFF_SECONDS = float(os.getenv("GEMINI_INITIAL_BACKOFF_SECONDS", "5"))
MAX_BACKOFF_SECONDS = float(os.getenv("GEMINI_MAX_BACKOFF_SECONDS", "300"))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("GEMINI_MAX_CONSECUTIVE_FAILURES", "5"))

SYSTEM_PROMPT = """You are an expert statistical classifier for the UN COICOP 2018 taxonomy (Classification of Individual Consumption According to Purpose). I will give you a list of e-commerce product names from Cambodia. You must return a JSON array mapping each product to its most specific 5-digit COICOP code. If unsure, return '99.9.9'. Include a 'confidence_score' (0.0 to 1.0) and a brief 'reasoning' string.

Classification rules:
- Use the official dotted 5-digit COICOP 2018 notation, e.g. '01.1.1' (Bread and cereals) or '07.2.2' (Fuels and lubricants for personal transport equipment).
- Prefer the MOST SPECIFIC code the name unambiguously supports. Never invent a finer class than the name justifies.
- If the product cannot be confidently mapped to any COICOP class, return the special code '99.9.9'.
- Classify only what the name literally describes. Do not infer bundles, promotions or brand-only categories unless the name says so.
- 'product_name' in the response MUST exactly match the input name so results can be joined back.
- 'confidence_score' must be a float from 0.0 to 1.0.
- 'reasoning' must be a short (max 15 words) English explanation.

CRITICAL store-context rules:
- This data comes from RETAIL GROCERY STORES. Packaged/retail food products —
  sandwiches, burgers, pizza, instant noodles, canned soup, ready meals,
  frozen dishes, pastries, sushi packs — are FOOD (division 01), even when
  named after restaurant dishes. Division 11 is ONLY for actual restaurant
  meals, cafe orders, or hotel accommodation services sold as a service
  (e.g. 'Dinner buffet for 2', 'Deluxe room 1 night').
- Phone/electronics ACCESSORIES (chargers, cases, FM transmitters, cables)
  bought at general retailers are NOT division 08. Classify by product type:
  car gadgets -> 07.2.1, audio/electronics -> 09.1.x. Division 08 equipment
  applies to phones/tablets themselves or telecom-store context.

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
- "Exercise Book A4 120 Pages" -> 09.5.4 (Stationery)
- "Electric Kettle 1.8L" -> 05.4.1 (Small electric household appliances)
- "Regular Gasoline" -> 07.2.2 (Fuels and lubricants)
- "USD/KHR Exchange Rate" -> 99.9.9 (Not a consumer good)
- "Smart Laor! 8GB Weekly" -> 08.4.0 (Other communication services)
- "Smart Fiber+ 80 Mbps" -> 08.3.0 (Internet services)
- "BIC Ball Pen Blue" -> 09.5.4 (Stationery)
- "Crayola Crayons 24 Colors" -> 09.5.4 (Stationery)
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
    from pipeline.config import alternate_host_url, get_database_url

    conn_str = get_database_url().replace(
        "postgresql://", "postgresql+psycopg2://", 1
    )
    try:
        eng = create_engine(conn_str)
        with eng.connect():
            pass
        return eng
    except Exception:
        return create_engine(alternate_host_url(conn_str))



def _normalize_name(name: str) -> str:
    """Cache key for a product name: case-folded and whitespace-normalized."""
    return re.sub(r"\s+", " ", str(name)).strip().lower()


def _get_api_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


class GeminiModelPool:
    """Manages a pool of Gemini API keys with round-robin rotation and automatic quota failover."""

    def __init__(self, keys: list[str], model_name: str = DEFAULT_MODEL):
        if not keys:
            raise RuntimeError("No Gemini API keys provided to GeminiModelPool")
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
                if _is_rate_limit_error(exc) or _is_quota_exhausted_error(exc):
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


def _build_model(keys: list[str] | None = None, model_name: str | None = None):
    if genai is None:
        raise RuntimeError(
            "google-generativeai is required (pip install google-generativeai)"
        )
    api_keys = keys or _get_api_keys()
    if not api_keys:
        raise RuntimeError(
            "GEMINI_API_KEY is not set; Gemini COICOP classification cannot run"
        )
    model_name = model_name or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    log.info(
        "Building Gemini Model Pool with %d key(s) for model %s with JSON mode",
        len(api_keys),
        model_name,
    )
    return GeminiModelPool(api_keys, model_name=model_name)


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


def _is_rate_limit_error(exc: Exception) -> bool:
    """True when the exception looks like a Google API quota/429 rejection."""
    msg = str(exc)
    return "429" in msg or "ResourceExhausted" in msg or "quota" in msg.lower()


def _is_quota_exhausted_error(exc: Exception) -> bool:
    """True when the error indicates the account request/token quota has been exhausted."""
    msg = str(exc)
    return (
        "free_tier_requests" in msg
        or "quota exceeded" in msg.lower()
        or "limit: 500" in msg
        or "exceeded your current quota" in msg.lower()
    )


def _extract_retry_delay(exc: Exception) -> float:
    """Extracts suggested retry delay in seconds from the exception message, if available."""
    msg = str(exc)
    m = re.search(r"retry\s+in\s+([0-9]+(?:\.[0-9]+)?)\s*s", msg, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m2 = re.search(r"seconds:\s*([0-9]+)", msg)
    if m2:
        return float(m2.group(1))
    return RATE_LIMIT_BACKOFF_SECONDS


def classify_batch(model, names: list[str]) -> list[dict[str, Any]]:
    """
    Sends one batch of product names to Gemini in JSON mode and parses the
    returned array. On a rate-limit (429/ResourceExhausted) response, backs
    off once and retries; any other error raises so the caller can mark the
    batch as failed.
    """
    for attempt in (1, 2):
        try:
            response = model.generate_content([SYSTEM_PROMPT] + [str(n) for n in names])
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 1 and _is_rate_limit_error(exc):
                if _is_quota_exhausted_error(exc):
                    # Hard daily/free-tier quota exceeded; retrying immediately won't succeed
                    raise
                backoff = min(_extract_retry_delay(exc), RATE_LIMIT_BACKOFF_SECONDS)
                log.warning(
                    "Gemini rate limit hit; backing off %.0fs then retrying batch of %d",
                    backoff,
                    len(names),
                )
                time.sleep(backoff)
                continue
            raise
    try:
        results = _parse_json_array(response.text)
    except (json.JSONDecodeError, ValueError) as parse_err:
        log.warning(
            "Gemini returned unparseable JSON for batch of %d names: %s. "
            "Falling back to unclassified for this batch.",
            len(names), parse_err,
        )
        return []

    # Phase 1: Detect truncated response from larger batch sizes
    if len(results) < len(names) * 0.8:
        log.warning(
            "Batch response incomplete: sent %d names, got %d results. "
            "Consider reducing GEMINI_BATCH_SIZE.",
            len(names), len(results),
        )

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        code = str(item.get("coicop_code") or UNCLASSIFIED).strip()
        classification_method = "model"
        confidence = float(item.get("confidence_score") or 0.0)
        # H4 FIX: 13.* is invalid per COICOP (no Division 13). Model sometimes
        # hallucinates it. Instead of silently rewriting 13.* → 12.*, record
        # the fallback and downgrade confidence so downstream can filter/flag.
        if code.startswith("13."):
            code = "12." + code[3:]
            classification_method = "model_fallback_rewrite"
            confidence = min(confidence, 0.5)  # cap confidence for rewritten codes
        normalized.append(
            {
                "product_name": str(item.get("product_name") or "").strip(),
                "coicop_code": code,
                "confidence_score": confidence,
                "reasoning": str(item.get("reasoning") or ""),
                "classification_method": classification_method,
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
    consecutive_failures = 0
    current_backoff = INITIAL_BACKOFF_SECONDS
    for idx, batch in enumerate(api_batches):
        if idx > 0:
            time.sleep(BATCH_DELAY_SECONDS)
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
            # Reset backoff on success
            consecutive_failures = 0
            current_backoff = INITIAL_BACKOFF_SECONDS
        except Exception as exc:  # noqa: BLE001 - one bad batch must not kill the run
            failed += 1
            consecutive_failures += 1
            log.warning("Gemini batch %d/%d of %d name(s) failed (consecutive=%d): %s",
                        idx + 1, len(api_batches), len(batch), consecutive_failures, exc)
            for name in batch:
                seen.setdefault(name, _unclassified_result(name))

            # Hard abort: daily/free-tier quota fully exhausted — retrying won't help today
            if _is_quota_exhausted_error(exc):
                remaining_batches = api_batches[idx + 1 :]
                remaining_count = sum(len(b) for b in remaining_batches)
                log.error(
                    "Gemini daily quota exhausted. Aborting remaining %d batch(es) (%d items); "
                    "the dbt rule ladder will classify these products.",
                    len(remaining_batches), remaining_count,
                )
                for rem_batch in remaining_batches:
                    for name in rem_batch:
                        seen.setdefault(name, _unclassified_result(name))
                break

            # Soft abort: too many consecutive failures — stop burning time
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                remaining_batches = api_batches[idx + 1 :]
                remaining_count = sum(len(b) for b in remaining_batches)
                log.error(
                    "Too many consecutive failures (%d). Aborting remaining %d batch(es) (%d items).",
                    consecutive_failures, len(remaining_batches), remaining_count,
                )
                for rem_batch in remaining_batches:
                    for name in rem_batch:
                        seen.setdefault(name, _unclassified_result(name))
                break

            # Adaptive exponential backoff: 5s → 10s → 20s → 40s → ... → 300s max
            if _is_rate_limit_error(exc):
                log.info(
                    "Rate limited — backing off %.0fs before batch %d/%d.",
                    current_backoff, idx + 2, len(api_batches),
                )
                time.sleep(current_backoff)
                current_backoff = min(current_backoff * 2, MAX_BACKOFF_SECONDS)

    return {
        "results": seen,
        "cache_hits": cache_hits,
        "api_calls": api_calls,
        "failed": failed,
    }


def _unclassified_result(name: str) -> dict[str, Any]:
    return {
        "product_name": name,
        "coicop_code": UNCLASSIFIED,
        "confidence_score": 0.0,
        "reasoning": "Gemini call failed; left unclassified",
    }


def triage_with_local_model(
    items: list[dict[str, Any]],
    confidence_threshold: float = 0.60,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Phase 3: Pre-classifies items using the local HybridCOICOPClassifier.

    High-confidence vector/store_purity matches skip the Gemini API entirely.

    Returns:
        - needs_gemini: items below threshold (must be sent to API)
        - local_results: dict of name -> result for high-confidence local matches
    """
    from pipeline.hybrid_embeddings_classifier import get_hybrid_classifier

    needs_gemini: list[dict[str, Any]] = []
    local_results: dict[str, dict[str, Any]] = {}

    try:
        classifier = get_hybrid_classifier()
    except Exception as exc:
        log.warning("Could not initialize local classifier for triage: %s", exc)
        return items, local_results

    for item in items:
        name = item.get("canonical_name", "")
        if not name or not name.strip():
            needs_gemini.append(item)
            continue

        try:
            result = classifier.classify_product(name)
            conf = result.get("confidence_score", 0.0)
            method = result.get("classification_method", "")

            # Accept local result only for store_purity (exact known code).
            # Vector embedding returns division-level reference codes (e.g. 01.1.1
            # for all food) which are too imprecise for full COICOP classification —
            # those items still need Gemini for precise 5-digit code assignment.
            if conf >= confidence_threshold and method == "store_purity":
                local_results[name] = {
                    "product_name": name,
                    "coicop_code": result.get("coicop_code", UNCLASSIFIED),
                    "confidence_score": conf,
                    "reasoning": f"Local triage: {result.get('reasoning', '')}",
                    "classification_method": f"local_{method}",
                }
                continue
        except Exception:
            pass

        needs_gemini.append(item)

    log.info(
        "Local triage: %d classified locally (>=%.0f%%), %d need Gemini API",
        len(local_results), confidence_threshold * 100, len(needs_gemini),
    )
    return needs_gemini, local_results


def _get_24h_interval_sql(engine: Any) -> str:
    """Return SQL dialect-compatible expression for a 24-hour lookback cutoff."""
    if getattr(getattr(engine, "dialect", None), "name", "") == "sqlite":
        return "datetime('now', '-24 hours')"
    return "CURRENT_TIMESTAMP - INTERVAL '24 hours'"


def fetch_unclassified(
    engine, scrape_date: str | None = None, limit: int = 5000,
) -> list[dict[str, Any]]:
    """Returns unclassified products present in the current scrape_date run ready for Gemini.

    Two-tier source order:
      1. silver.classification_queue (PENDING rows) — products the dbt ladder
         routed to human review because no rule tier matched.
      2. AI sweep over silver.int_prices_cleaned ⋈ silver.canonical_items for the
         specified scrape_date where the canonical name has no entry in
         silver.dim_coicop_ai_cache (or only a stale negative cache entry > 24h old).
         Pure single-division stores are skipped (store purity outranks AI in
         the dbt resolution order, so spending API calls on them is unnecessary).

    Phase 4: Excludes products with a recent (< 24h) negative cache entry to
    prevent retry storms on genuinely unclassifiable items.
    Phase 5: Accepts a ``limit`` parameter for chunked Airflow scheduling.
    Phase 6: Orders by observation frequency so high-value products are classified first.
    """
    items: list[dict[str, Any]] = []
    with engine.connect() as conn:
        # Tier 1: PENDING rows in the classification triage queue.
        try:
            q_res = conn.execute(
                text(
                    "SELECT product_key as canonical_item_id, name_clean as canonical_name "
                    "FROM silver.classification_queue "
                    "WHERE status = 'PENDING' "
                    "LIMIT :lim"
                ),
                {"lim": limit},
            ).fetchall()
            for r in q_res:
                items.append(
                    {"canonical_item_id": str(r[0]), "canonical_name": str(r[1])}
                )
        except Exception as e:
            log.warning("Could not read silver.classification_queue: %s", e)

        # Tier 2: Sweep every uncached product scraped on this specific scrape_date
        if not items:
            try:
                date_filter = "p.scrape_date = CAST(:ds AS DATE)" if scrape_date else "p.scrape_date = (SELECT max(scrape_date) FROM silver.int_prices_cleaned)"
                # Phase 4: Exclude recently negative-cached items (< 24h old)
                interval_clause = _get_24h_interval_sql(engine)
                # Phase 6: Order by observation count DESC (most-seen products first)
                query_sql = f"""
                    SELECT sub.item_id, sub.canonical_name, sub.observation_count
                    FROM (
                        SELECT DISTINCT p.item_id::text AS item_id, ci.canonical_name,
                               COUNT(*) OVER (PARTITION BY p.item_id) AS observation_count
                        FROM (
                            SELECT DISTINCT item_id, store_slug, scrape_date
                            FROM silver.int_prices_cleaned p
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
                        WHERE (ai.coicop_code IS NULL
                               OR (ai.coicop_code = '99.9.9'
                                   AND ai.classified_at < {interval_clause}))
                          AND ci.canonical_name IS NOT NULL
                          AND length(trim(ci.canonical_name)) > 1
                    ) sub
                    ORDER BY sub.observation_count DESC, sub.canonical_name
                    LIMIT :lim
                """
                params: dict[str, Any] = {"lim": limit}
                if scrape_date:
                    params["ds"] = scrape_date
                ci_res = conn.execute(text(query_sql), params).fetchall()
                for r in ci_res:
                    items.append(
                        {"canonical_item_id": str(r[0]), "canonical_name": str(r[1])}
                    )
            except Exception as e:
                log.warning("Could not fetch unclassified items: %s", e)

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

    Phase 4: '99.9.9' (unclassified) outcomes are now cached as negative entries
    so they won't be retried for 24 hours (see fetch_unclassified). Previously
    they were never cached, causing retry storms on genuinely unclassifiable items.
    """
    positive_rows = [
        r
        for r in results.values()
        if r.get("confidence_score", 0.0) > 0.0 and r.get("coicop_code") != UNCLASSIFIED
    ]
    negative_rows = [
        r
        for r in results.values()
        if r.get("coicop_code") == UNCLASSIFIED and r.get("product_name")
    ]

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
    # Phase 4: Negative cache — only update if existing entry is > 24h old
    interval_clause = _get_24h_interval_sql(engine)
    neg_stmt = text(
        f"""
        INSERT INTO silver.dim_coicop_ai_cache
            (product_name, coicop_code, confidence_score, reasoning, model_version)
        VALUES (:name, '99.9.9', 0.0, :reasoning, :model)
        ON CONFLICT (product_name) DO UPDATE
        SET classified_at = CURRENT_TIMESTAMP,
            reasoning = EXCLUDED.reasoning
        WHERE dim_coicop_ai_cache.classified_at < {interval_clause}
           OR dim_coicop_ai_cache.coicop_code = '99.9.9'
        """
    )
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    n = 0
    n_neg = 0
    with engine.begin() as conn:
        for row in positive_rows:
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
        for row in negative_rows:
            conn.execute(
                neg_stmt,
                {
                    "name": row["product_name"],
                    "reasoning": row.get("reasoning", "Gemini returned unclassified"),
                    "model": model,
                },
            )
            n_neg += 1
    log.info(
        "Upserted %d positive + %d negative row(s) into dim_coicop_ai_cache",
        n, n_neg,
    )
    return n


def persist_classifications(
    engine,
    results: dict[str, dict[str, Any]],
    items: list[dict[str, Any]],
    scrape_date: str | None = None,
) -> int:
    """Resolve silver.classification_queue rows whose product name received a
    fresh Gemini classification.

    High-confidence matches (>= 0.50) flip the queue row to RESOLVED with the
    derived 2-digit division; low-confidence matches (< 0.50) stay PENDING with
    a 'low confidence AI classification' reason for future AI sweep re-evaluation.

    Note: the COICOP code itself is NOT written here — it lives in
    silver.dim_coicop_ai_cache (see update_cache), which is what
    int_coicop_classified.sql tier 3 consults. This function only maintains the
    operational triage state.
    """
    by_name = {
        _normalize_name(i["canonical_name"]): i["canonical_item_id"] for i in items
    }
    updates: list[dict[str, Any]] = []
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

    n_queue = 0
    try:
        with engine.begin() as conn:
            for row in updates:
                is_low_conf = row["confidence_score"] < 0.50
                division = row["coicop_code"].split(".")[0].zfill(2)
                if division == "13":
                    division = "12"
                if is_low_conf:
                    res_q = conn.execute(
                        update_queue_pending_sql,
                        {"canonical_item_id": str(row["canonical_item_id"])},
                    )
                else:
                    res_q = conn.execute(
                        update_queue_resolved_sql,
                        {
                            "canonical_item_id": str(row["canonical_item_id"]),
                            "division": division,
                        },
                    )
                n_queue += res_q.rowcount or 0
    except Exception as exc:
        log.warning("classification_queue batch update failed: %s", exc)
    log.info(
        "Persisted Gemini COICOP queue state: %d row(s) updated (cache writes happen via update_cache)",
        n_queue,
    )
    return n_queue


def classify_unclassified_with_gemini(
    engine=None,
    scrape_date: str | None = None,
    batch_size: int = BATCH_SIZE,
    model=None,
    max_products: int = 5000,
) -> dict[str, Any]:
    """
    Gemini AI COICOP classification entry point (Airflow PythonOperator callable).

    Classifies every product still at '99.9.9':
      Phase 3: Local triage first (vector/store_purity) to avoid unnecessary API calls.
      Then Gemini JSON mode in batches for the remaining ambiguous products.
      Phase 5: ``max_products`` caps how many items are fetched per run for chunked scheduling.
    """
    engine = engine or get_engine()
    items = fetch_unclassified(engine, scrape_date=scrape_date, limit=max_products)
    if not items:
        log.info("No unclassified products to classify with Gemini")
        return {"status": "SKIPPED_NO_UNCLASSIFIED", "candidates": 0, "classified": 0}

    # Phase 3: Local-first triage — classify high-confidence items locally
    items_for_gemini, local_results = triage_with_local_model(items)

    cache = load_cache(engine)
    # Only send remaining ambiguous items to Gemini
    names = [i["canonical_name"] for i in items_for_gemini]
    if names:
        outcome = classify_names(names, model=model, cache=cache, batch_size=batch_size)
    else:
        outcome = {"results": {}, "cache_hits": 0, "api_calls": 0, "failed": 0}

    # Merge local + Gemini results (Gemini overwrites local if both have a result)
    all_results = {**local_results, **outcome["results"]}

    update_cache(engine, all_results)
    n_mapping = persist_classifications(engine, all_results, items, scrape_date)

    classified = sum(
        1 for r in all_results.values() if r["coicop_code"] != UNCLASSIFIED
    )
    return {
        "status": "OK",
        "candidates": len(items),
        "classified_locally": len(local_results),
        "sent_to_gemini": len(names),
        "classified": classified,
        "cache_hits": outcome["cache_hits"],
        "api_calls": outcome["api_calls"],
        "failed_batches": outcome["failed"],
        "mapping_rows_updated": n_mapping,
    }
