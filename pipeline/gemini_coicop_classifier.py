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

SYSTEM_PROMPT = """You are an expert statistical classifier for the UN COICOP 2018 taxonomy (Classification of Individual Consumption According to Purpose).
I will give you a list of e-commerce products from Cambodia. Each item may be provided as either:
  1. A plain product name string, OR
  2. A JSON object with context: {"name": "...", "store": "...", "category": "...", "price_khr": ...}

Use all provided contextual signals (store name, native category hierarchy, price) to accurately disambiguate the item.
You must return a JSON array mapping each product to its most specific 5-digit COICOP code. If unsure, return '99.9.9'.
Include a 'confidence_score' (0.0 to 1.0) and a brief 'reasoning' string.

Classification rules:
- Use official dotted 5-digit COICOP 2018 notation, e.g. '01.1.1' (Bread and cereals) or '07.2.2' (Fuels and lubricants).
- Prefer the MOST SPECIFIC code the name unambiguously supports. Never invent a finer class than the name justifies.
- If the product cannot be confidently mapped to any COICOP class, return the special code '99.9.9'.
- Classify only what the name literally describes. Do not infer bundles, promotions or brand-only categories unless the name says so.
- 'product_name' in the response MUST exactly match the input name so results can be joined back.
- 'confidence_score' must be a float from 0.0 to 1.0 (>= 0.85 for unambiguous items).
- 'reasoning' must be a short (max 20 words) English explanation.

CRITICAL retail context & trap disambiguation rules:
- RETAIL SUPERMARKET FOOD IS ALWAYS DIVISION 01: Packaged, canned, fresh, or prepared retail grocery products —
  sandwiches, burgers, pizza, instant noodles, canned soup, ready meals, bento boxes,
  frozen dishes, pastries, sushi packs, salad packs — are FOOD (division 01), NEVER division 11.
- Division 11 is RESERVED EXCLUSIVELY for actual dine-in restaurant services, cafe bills, or hotel overnight room bookings.
- Division 04 is RESERVED for residential real estate rentals and utility bills. Hardware, cookware, and groceries are NEVER division 04.
- CULINARY WINE / MIRIN / SAKE: "Cooking Wine", "Shaoxing Wine for Cooking", "Mirin" are seasonings -> 01.1.9 (Food n.e.c.), NEVER 02.1.2 (Wine).
- NON-ALCOHOLIC BEVERAGES: 0.0% alcohol-free beer/cider -> 01.2.2 (Soft drinks). Real beer/cider (e.g. Somersby, Angkor, Cambodia Beer) -> 02.2.1.
- ACCESSORY TRAPS: "Coffee Filter", "Tea Strainer/Infuser", "Ice Tray" -> 05.5.1 (Household utensils), NEVER 01.2.1 (Coffee/Tea).
- APPAREL TRAPS: "Slippers", "Bath Slippers", "Sandals" -> 03.2.1 (Footwear), NEVER 05.2.1 (Household linen).
- CLEANING TRAPS: Floor cleaner, dishwashing liquid, laundry detergent, bleach, air freshener, trash bags -> 05.6.1 (Non-durable household goods).
- PERSONAL CARE TRAPS: Hair clippers, shavers, haircut tools, electric toothbrushes, hair dryers -> 12.1.3 (Personal care appliances).
- STATIONERY VS TRAVEL GOODS: Notebooks, exercise books, pencils, pens, crayons -> 09.5.4 (Stationery). School backpacks, travel backpacks, suitcases -> 12.2.1 (Travel goods).
- COSMETICS & SUNCARE: Sunscreen (e.g. Skin Aqua), lip balm, face cream, moisturizer, shampoo, body wash -> 12.1.3 (Personal care).
- OTC MEDICINES & PHARMACEUTICALS: Throat lozenges, cough drops, painkillers, paracetamol, bandages, vitamins -> 06.1.2.
- ELECTRONICS VS ACCESSORIES: Smartphones/tablets -> 08.2.0. Cables/chargers/audio -> 09.1.1 or 09.1.3. Car mount/charger -> 07.2.1.

Common UN COICOP 2018 5-digit codes:
- 01.1.1 Bread, cereals and ready dishes (rice, flour, pasta, cereal, noodles, bread, buns, croissants, pizza, ready meals, bento, sandwiches)
- 01.1.2 Meat (fresh/frozen beef, pork, chicken, poultry, sausages, bacon, ham, jerky, dried meat)
- 01.1.3 Fish and seafood (fresh/frozen fish, salmon, canned tuna, shrimp, squid, crab, dried fish)
- 01.1.4 Milk, cheese and eggs (fresh milk, yogurt, cheese, eggs, butter, condensed milk, powdered milk, baby formula)
- 01.1.5 Oils and fats (cooking oil, vegetable oil, olive oil, coconut oil, sesame oil, margarine, ghee)
- 01.1.6 Fruit (fresh fruit, dried fruit, frozen fruit, apples, bananas, oranges, mango, grapes)
- 01.1.7 Vegetables (fresh/frozen/canned vegetables, potatoes, onions, tomatoes, mushrooms, fresh salad, garlic, chili)
- 01.1.8 Sugar, jam, honey, chocolate and confectionery (sugar, honey, jam, chocolate, candy, cookies, biscuits, wafers, cakes)
- 01.1.9 Food products n.e.c. (cooking wine, mirin, sauces, soy sauce, fish sauce, oyster sauce, chili sauce, ketchup, mayonnaise, mustard, vinegar, salt, pepper, spices, seasoning)
- 01.2.1 Coffee, tea and cocoa (ground coffee, coffee beans, instant coffee, tea bags, green tea, cocoa powder)
- 01.2.2 Mineral waters, soft drinks, juices (bottled drinking water, mineral water, soda, fruit juice, energy drink, canned iced tea/coffee, 0.0% non-alcoholic beer)
- 02.1.1 Spirits (whiskey, vodka, rum, gin, tequila, brandy, soju, baijiu)
- 02.1.2 Wine (red wine, white wine, rose, champagne, sparkling wine)
- 02.2.1 Beer and cider (beer, lager, stout, pilsner, ale, craft beer, apple cider)
- 02.2.0 Tobacco (cigarettes, cigars, tobacco)
- 03.1.1 Garments for men (men shirt, men pants, men jacket, men shorts)
- 03.1.2 Garments for women (women dress, women blouse, women skirt, women pants)
- 03.1.3 Garments for infants (baby clothes, baby bodysuit, baby pajamas)
- 03.1.4 Other garments (unisex clothing, apron, raincoat, underwear, socks)
- 03.2.1 Shoes and other footwear (shoes, sneakers, boots, sandals, flip-flops, slippers, bath slippers)
- 04.1.1 Actual rentals for housing (apartment rent, condo rent, house rental)
- 04.5.1 Electricity (electric bill, power bill)
- 04.5.2 Gas (gas cylinder, lpg refill)
- 05.1.1 Furniture and furnishings (sofa, chair, table, bed, desk, mattress)
- 05.2.1 Household textiles (towel, curtains, bedsheet, pillow, blanket)
- 05.3.1 Major household appliances (refrigerator, washing machine, air conditioner)
- 05.4.1 Small electric household appliances (kettle, blender, rice cooker, toaster, iron, microwave)
- 05.5.1 Glassware, tableware and household utensils (plate, bowl, cup, pan, pot, wok, knife, cutlery, coffee filter, tea infuser)
- 05.6.1 Non-durable household goods (laundry detergent, dishwashing soap, bleach, floor cleaner, sponges, trash bags, air freshener)
- 06.1.1 Medical services (doctor visit, clinic)
- 06.1.2 Pharmaceutical products (paracetamol, ibuprofen, antibiotic, cough syrup, throat lozenge, vitamins, first aid, medical mask)
- 07.1.2 Passenger transport by road (bus ticket, van ticket, taxi fare)
- 07.2.1 Spare parts and accessories for transport equipment (tires, car battery, spark plug, motor oil filter, car phone holder)
- 07.2.2 Fuels and lubricants for transport equipment (gasoline, petrol, diesel, engine oil)
- 08.2.0 Telephone and telefax equipment (smartphone, mobile phone, tablet, iPad)
- 08.3.0 Internet and telecom services (internet plan, wifi subscription, data plan, SIM card, airtime)
- 09.1.1 Audio-visual equipment (TV, headphone, speaker, camera)
- 09.1.3 Information processing equipment (laptop, PC, printer)
- 09.3.4 Pets and related products (dog food, cat food, pet treats, cat litter, pet shampoo)
- 09.5.4 Stationery and drawing materials (notebook, exercise book, pen, pencil, eraser, ruler, stapler, crayon)
- 11.1.1 Restaurants and cafes (dine-in meal bill, cafe table order, restaurant dining)
- 11.2.0 Accommodation services (hotel room overnight stay, resort booking)
- 12.1.3 Articles and products for personal care (shampoo, hair conditioner, body wash, lotion, sunscreen, skincare, face cream, makeup, perfume, toothpaste, toothbrush, haircut clippers, shavers, toilet paper, diapers, wet wipes)
- 12.2.1 Travel goods and personal effects (backpack, school bag, suitcase, handbag, wallet, umbrella)

Cambodian market examples:
- "Jasmine Rice 5kg" -> 01.1.1 (Bread, cereals and grain products)
- "Frozen Cheese Pizza 350g" -> 01.1.1 (Bread, cereals and ready dishes)
- "Pork Fried Rice (Bai Cha) Ready Meal" -> 01.1.1 (Bread, cereals and ready dishes)
- "Karaage-Don Bento Box" -> 01.1.1 (Bread, cereals and ready dishes)
- "Fresh Pork Belly 500g" -> 01.1.2 (Meat)
- "Salmon Fillet Fresh 200g" -> 01.1.3 (Fish and seafood)
- "Dutch Mill Fresh Milk 1L" -> 01.1.4 (Milk, cheese and eggs)
- "Vegetable Cooking Oil 1L" -> 01.1.5 (Oils and fats)
- "Fresh Cavendish Banana 1kg" -> 01.1.6 (Fruit)
- "Broccoli Fresh 500g" -> 01.1.7 (Vegetables)
- "COOKING WINE 750ML" -> 01.1.9 (Food products n.e.c. - cooking condiment)
- "Chili Sauce Sriracha 450g" -> 01.1.9 (Food products n.e.c. - sauces and condiments)
- "Fish Sauce 750ml" -> 01.1.9 (Food products n.e.c. - sauces and condiments)
- "Iced Coffee 250ml Can" -> 01.2.2 (Mineral waters, soft drinks, juices)
- "Angkor Beer Can 330ml" -> 02.2.1 (Beer)
- "SOMERSBY CIDER 4X330ML" -> 02.2.1 (Beer and cider)
- "Men Cotton T-Shirt" -> 03.1.1 (Garments for men)
- "TVHC SLIPPER UNISEX" -> 03.2.1 (Footwear - slippers)
- "1 Bedroom Condo BKK1 Monthly Rent" -> 04.1.1 (Actual rentals for housing)
- "TV COFFEE FILTER 40" -> 05.5.1 (Tableware and household utensils)
- "Non-Stick Frying Pan 28cm" -> 05.5.1 (Tableware and household utensils)
- "Sunlight Dishwashing Liquid 750ml" -> 05.6.1 (Non-durable household goods)
- "Attack Laundry Detergent 1.4kg" -> 05.6.1 (Non-durable household goods)
- "LIX FLOOR CLEANER 3.8L" -> 05.6.1 (Non-durable household goods)
- "Panadol Extra 500mg 10s" -> 06.1.2 (Pharmaceutical products)
- "GOLDEN THROAT LOZENGE PACK" -> 06.1.2 (Pharmaceutical products)
- "Bus Ticket Phnom Penh - Siem Reap" -> 07.1.2 (Passenger transport by road)
- "Regular Gasoline 1L" -> 07.2.2 (Fuels and lubricants)
- "Samsung Galaxy A15 128GB" -> 08.2.0 (Telephone equipment)
- "Smart Fiber 50 Mbps Monthly" -> 08.3.0 (Internet services)
- "Sony Wireless Headphones" -> 09.1.1 (Audio-visual equipment)
- "Pedigree Dog Food Beef 1.5kg" -> 09.3.4 (Pets and related products)
- "EXERCISE BOOK A4" -> 09.5.4 (Stationery and drawing materials)
- "Deluxe Hotel Room 1 Night Stay" -> 11.2.0 (Accommodation services)
- "Head & Shoulders Shampoo 450ml" -> 12.1.3 (Articles and products for personal care)
- "HAIRCUT CLIPPER RECHARGEABLE" -> 12.1.3 (Personal care appliances)
- "SUNPLAY SKIN AQUA SPF50" -> 12.1.3 (Articles and products for personal care)
- "Colgate Total Toothpaste 150g" -> 12.1.3 (Articles and products for personal care)
- "Foldable Travel Backpack 20L" -> 12.2.1 (Travel goods and personal effects)
- "SCHOOL BACKPACK" -> 12.2.1 (Travel goods and personal effects)

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


COICOP_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "product_name": {"type": "STRING"},
            "coicop_code": {"type": "STRING"},
            "confidence_score": {"type": "NUMBER"},
            "reasoning": {"type": "STRING"},
        },
        "required": ["product_name", "coicop_code", "confidence_score"],
    },
}


def _build_generation_config() -> Any:
    """Builds a GenerationConfig with JSON schema enforcement if supported."""
    if genai is None:
        return None
    try:
        return genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=COICOP_RESPONSE_SCHEMA,
        )
    except Exception:
        return genai.GenerationConfig(response_mime_type="application/json")


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
                gen_config = _build_generation_config()
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    generation_config=gen_config,
                )
                return model.generate_content(contents, **kwargs)
            except Exception as exc:
                last_exc = exc
                if _is_quota_exhausted_error(exc):
                    self.mark_exhausted(key)
                    if self.active_keys:
                        log.info(
                            "Hard quota exceeded. Failing over to next Gemini API key (%d active keys left)...",
                            len(self.active_keys),
                        )
                        continue
                elif _is_rate_limit_error(exc):
                    # Transient RPM rate limit: do not permanently kill key; rotate to next active key
                    log.warning(
                        "Transient rate limit hit on Gemini key (%s...). Rotating to next active key...",
                        key[:12] if len(key) >= 12 else key,
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


def _format_item_for_prompt(item: Any) -> str:
    """Formats an item (either string name or dict with metadata) for the Gemini prompt."""
    if isinstance(item, dict):
        name = item.get("canonical_name") or item.get("product_name") or ""
        # Only format as JSON object if extra contextual signals exist
        has_context = bool(
            item.get("store_slug")
            or item.get("category_native")
            or item.get("price_khr") is not None
        )
        if has_context:
            ctx: dict[str, Any] = {"name": name}
            if item.get("store_slug"):
                ctx["store"] = item["store_slug"]
            if item.get("category_native"):
                ctx["category"] = item["category_native"]
            if item.get("price_khr") is not None:
                ctx["price_khr"] = item["price_khr"]
            return json.dumps(ctx, ensure_ascii=False)
        return str(name)
    return str(item)


def _get_item_name(item: Any) -> str:
    """Extracts raw product name from a string or dictionary item."""
    if isinstance(item, dict):
        return str(item.get("canonical_name") or item.get("product_name") or "").strip()
    return str(item).strip()


def classify_batch(model, names: list[Any]) -> list[dict[str, Any]]:
    """
    Sends one batch of product names (strings or context dicts) to Gemini in JSON mode
    and parses the returned array. On a rate-limit (429/ResourceExhausted) response,
    backs off once and retries; any other error raises so the caller can mark the
    batch as failed.
    """
    for attempt in (1, 2):
        try:
            prompt_items = [_format_item_for_prompt(n) for n in names]
            response = model.generate_content([SYSTEM_PROMPT] + prompt_items)
            break
        except Exception as exc:
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
    names: list[Any],
    model=None,
    cache: dict[str, dict[str, Any]] | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, Any]:
    """
    Classifies product names (or context dicts) using Gemini with per-name memoization.

    ``cache`` maps normalized product name -> cached result dict. Names with a
    cache hit never reach the API. Returns:
        {"results": {name: result}, "cache_hits": int, "api_calls": int, "failed": int}
    """
    if model is None:
        model = _build_model()

    cache = cache or {}
    seen: dict[str, dict[str, Any]] = {}

    # 1. Resolve every name: cache first, API second (in batches of 50).
    api_batches: list[list[Any]] = []
    batch: list[Any] = []
    for raw_item in names:
        item_str = _get_item_name(raw_item)
        key = _normalize_name(item_str)
        if key in cache:
            cached_val = cache[key]
            if (
                cached_val.get("coicop_code") not in (None, UNCLASSIFIED)
                and float(cached_val.get("confidence_score", 0.0)) >= 0.50
            ):
                seen[item_str] = dict(cached_val)
                continue
        batch.append(raw_item)
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
                # Match results back to input items via normalized key
                seen[item_name] = item
                for orig in batch:
                    orig_name = _get_item_name(orig)
                    if _normalize_name(orig_name) == key:
                        seen[orig_name] = item
            # Reset backoff on success
            consecutive_failures = 0
            current_backoff = INITIAL_BACKOFF_SECONDS
        except Exception as exc:  # one bad batch must not kill the run
            failed += 1
            consecutive_failures += 1
            log.warning("Gemini batch %d/%d of %d name(s) failed (consecutive=%d): %s",
                        idx + 1, len(api_batches), len(batch), consecutive_failures, exc)
            for raw_item in batch:
                name = _get_item_name(raw_item)
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
    """Triage unclassified items locally using pure store rules.

    Items from verified pure single-category stores are classified locally in O(1) time.
    Remaining multi-category store items are returned for Gemini API processing.
    """
    from pipeline.hybrid_embeddings_classifier import PURE_STORE_MAP

    needs_gemini: list[dict[str, Any]] = []
    local_results: dict[str, dict[str, Any]] = {}

    for item in items:
        name = item.get("canonical_name", "")
        store_slug = item.get("store_slug", "")
        if not name or not name.strip():
            needs_gemini.append(item)
            continue

        if store_slug and store_slug in PURE_STORE_MAP:
            _div, code = PURE_STORE_MAP[store_slug]
            local_results[name] = {
                "product_name": name,
                "coicop_code": code,
                "confidence_score": 1.0,
                "reasoning": f"Local triage: pure store {store_slug}",
                "classification_method": "local_store_purity",
            }
            continue

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

        # Tier 2: Sweep uncached products scraped on this specific scrape_date if slots remain
        remaining = limit - len(items)
        if remaining > 0:
            try:
                date_filter = "p.scrape_date = CAST(:ds AS DATE)" if scrape_date else "p.scrape_date = (SELECT max(scrape_date) FROM silver.int_prices_cleaned)"
                # Phase 4: Exclude recently negative-cached items (< 24h old)
                interval_clause = _get_24h_interval_sql(engine)
                # Phase 6: Order by observation count DESC (most-seen products first)
                query_sql = f"""
                    SELECT sub.item_id, sub.canonical_name, sub.store_slug, sub.category_native, sub.price_khr, sub.observation_count
                    FROM (
                        SELECT DISTINCT CAST(p.item_id AS TEXT) AS item_id, ci.canonical_name, p.store_slug,
                               p.category_native, p.price_khr,
                               COUNT(*) OVER (PARTITION BY p.item_id) AS observation_count
                        FROM (
                            SELECT DISTINCT item_id, store_slug, category_native, price_khr, scrape_date
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
                          ON CAST(ci.item_id AS TEXT) = CAST(p.item_id AS TEXT)
                        LEFT JOIN silver.dim_coicop_ai_cache ai
                          ON lower(trim(ai.product_name)) = lower(trim(ci.canonical_name))
                        WHERE (ai.coicop_code IS NULL
                               OR (ai.coicop_code = '99.9.9'
                                   AND ai.classified_at < {interval_clause})
                               OR (ai.confidence_score < 0.50
                                   AND ai.classified_at < {interval_clause}))
                          AND ci.canonical_name IS NOT NULL
                          AND length(trim(ci.canonical_name)) > 1
                    ) sub
                    ORDER BY sub.observation_count DESC, sub.canonical_name
                    LIMIT :lim
                """
                params: dict[str, Any] = {"lim": remaining}
                if scrape_date:
                    params["ds"] = scrape_date
                ci_res = conn.execute(text(query_sql), params).fetchall()

                # If int_prices_cleaned hasn't run yet for this scrape_date, discover from bronze + item_match_log
                if not ci_res and scrape_date:
                    fallback_sql = f"""
                        SELECT sub.item_id, sub.canonical_name, sub.store_slug, sub.category_native, sub.price_khr, sub.observation_count
                        FROM (
                            SELECT DISTINCT CAST(iml.item_id AS TEXT) AS item_id, ci.canonical_name, rp.store_id AS store_slug,
                                   rp.raw_payload ->> 'category_native' AS category_native,
                                   (CASE WHEN rp.currency = 'USD' THEN rp.price * 4044 ELSE rp.price END) AS price_khr,
                                   COUNT(*) OVER (PARTITION BY iml.item_id) AS observation_count
                            FROM bronze.raw_prices rp
                            JOIN silver.item_match_log iml ON iml.raw_price_id = rp.raw_price_id
                            JOIN silver.canonical_items ci ON CAST(ci.item_id AS TEXT) = CAST(iml.item_id AS TEXT)
                            LEFT JOIN silver.dim_coicop_ai_cache ai ON lower(trim(ai.product_name)) = lower(trim(ci.canonical_name))
                            WHERE rp.scraped_at::date = CAST(:ds AS DATE)
                              AND rp.store_id NOT IN (
                                  'communitypharma', 'khmer24', 'realestate',
                                  'sokhahotel', 'hyyathotel', 'hyatt', 'bayonbkk',
                                  'bookmebus', 'redbus', 'redmebus', 'new_gasoline',
                                  'arystore', 'samnangshop', 'cellcard', 'cellcard_wifi',
                                  'smart', 'smart_wifi'
                              )
                              AND (ai.coicop_code IS NULL
                                   OR (ai.coicop_code = '99.9.9'
                                       AND ai.classified_at < {interval_clause})
                                   OR (ai.confidence_score < 0.50
                                       AND ai.classified_at < {interval_clause}))
                              AND ci.canonical_name IS NOT NULL
                              AND length(trim(ci.canonical_name)) > 1
                        ) sub
                        ORDER BY sub.observation_count DESC, sub.canonical_name
                        LIMIT :lim
                    """
                    ci_res = conn.execute(text(fallback_sql), params).fetchall()

                for r in ci_res:
                    items.append(
                        {
                            "canonical_item_id": str(r[0]),
                            "canonical_name": str(r[1]),
                            "store_slug": str(r[2]) if len(r) > 2 and r[2] else "",
                            "category_native": str(r[3]) if len(r) > 3 and r[3] else "",
                            "price_khr": float(r[4]) if len(r) > 4 and r[4] is not None else None,
                        }
                    )
            except Exception as e:
                log.warning("Could not fetch unclassified items: %s", e)

    return items


def load_cache(engine, item_names: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Loads Gemini cache & verified Ground Truth labels keyed by normalized product name.
    If item_names is provided, queries only matching products for fast, memory-safe execution.
    """
    cache = {}
    with engine.connect() as conn:
        names_to_query = None
        if item_names:
            norm_map = {_normalize_name(name): name for name in item_names if name}
            names_to_query = list(set(list(norm_map.keys()) + [name for name in item_names if name]))

        # 1. Load AI Cache
        try:
            if names_to_query:
                if engine.dialect.name == "postgresql":
                    query = text(
                        "SELECT product_name, coicop_code, confidence_score, reasoning "
                        "FROM silver.dim_coicop_ai_cache "
                        "WHERE product_name = ANY(:names)"
                    )
                    rows = conn.execute(query, {"names": names_to_query}).fetchall()
                else:
                    from sqlalchemy import bindparam
                    query = text(
                        "SELECT product_name, coicop_code, confidence_score, reasoning "
                        "FROM silver.dim_coicop_ai_cache "
                        "WHERE product_name IN :names"
                    ).bindparams(bindparam("names", expanding=True))
                    rows = conn.execute(query, {"names": names_to_query}).fetchall()
            else:
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
            if names_to_query:
                if engine.dialect.name == "postgresql":
                    gt_query = text(
                        "SELECT product_name, coicop_code, confidence_score, notes "
                        "FROM silver.classification_ground_truth "
                        "WHERE product_name = ANY(:names)"
                    )
                    gt_rows = conn.execute(gt_query, {"names": names_to_query}).fetchall()
                else:
                    from sqlalchemy import bindparam
                    gt_query = text(
                        "SELECT product_name, coicop_code, confidence_score, notes "
                        "FROM silver.classification_ground_truth "
                        "WHERE product_name IN :names"
                    ).bindparams(bindparam("names", expanding=True))
                    gt_rows = conn.execute(gt_query, {"names": names_to_query}).fetchall()
            else:
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
    max_products: int | None = None,
) -> dict[str, Any]:
    """
    Gemini AI COICOP classification entry point (Airflow PythonOperator callable).

    Classifies newly scraped products:
      Phase 3: Fast local store purity triage to avoid unnecessary API calls.
      Phase 4: Prunes cached items before making API calls.
      Phase 5: Configurable limit via GEMINI_MAX_PRODUCTS_PER_RUN (default 500) for fast Airflow scheduling.
    """
    if max_products is None:
        max_products = int(
            os.getenv("GEMINI_MAX_PRODUCTS_PER_RUN")
            or os.getenv("GEMINI_MAX_ITEMS_PER_RUN", "500")
        )

    engine = engine or get_engine()
    items = fetch_unclassified(engine, scrape_date=scrape_date, limit=max_products)
    if not items:
        log.info("No unclassified products to classify with Gemini")
        return {"status": "SKIPPED_NO_UNCLASSIFIED", "candidates": 0, "classified": 0}

    # Phase 3: Fast local triage — classify pure-store items locally in O(1)
    items_for_gemini, local_results = triage_with_local_model(items)

    names_to_lookup = [i.get("canonical_name", "") for i in items_for_gemini if i.get("canonical_name")]
    cache = load_cache(engine, item_names=names_to_lookup)

    # Phase 4: Filter out items already in cache before sending to Gemini API
    # High-confidence entries (>= 0.50) are authoritative; low-confidence entries (< 0.50)
    # are re-sent to Gemini so they can be reliably classified and resolved.
    items_uncached = []
    cached_results: dict[str, dict[str, Any]] = {}
    for item in items_for_gemini:
        norm_name = _normalize_name(item.get("canonical_name", ""))
        cached_entry = cache.get(norm_name)
        if (
            cached_entry
            and cached_entry.get("coicop_code") not in (None, UNCLASSIFIED)
            and float(cached_entry.get("confidence_score", 0.0)) >= 0.50
        ):
            cached_results[item["canonical_name"]] = cached_entry
        else:
            items_uncached.append(item)

    # Only send remaining ambiguous items to Gemini with rich context
    if items_uncached:
        outcome = classify_names(items_uncached, model=model, cache=cache, batch_size=batch_size)
    else:
        outcome = {"results": {}, "cache_hits": 0, "api_calls": 0, "failed": 0}

    # Merge cached + local + Gemini results (Gemini overwrites local if both have a result)
    all_results = {**cached_results, **local_results, **outcome["results"]}

    update_cache(engine, all_results)
    n_mapping = persist_classifications(engine, all_results, items, scrape_date)

    classified = sum(
        1 for r in all_results.values() if r["coicop_code"] != UNCLASSIFIED
    )
    total_cache_hits = len(cached_results) + outcome.get("cache_hits", 0)
    return {
        "status": "OK",
        "candidates": len(items),
        "classified_locally": len(local_results),
        "sent_to_gemini": len(items_uncached),
        "classified": classified,
        "cache_hits": total_cache_hits,
        "api_calls": outcome["api_calls"],
        "failed_batches": outcome["failed"],
        "mapping_rows_updated": n_mapping,
    }
