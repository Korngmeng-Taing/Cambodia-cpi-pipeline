#!/usr/bin/env python3
"""
scripts/classify_local.py
─────────────────────────
Rules-based local classification for items in clean_store_prices NOT in canonical_items.
Uses store-slug pure domain mapping + name keyword matching. No API calls needed.
"""
import sys
sys.path.insert(0, ".")
import argparse
import logging
import uuid
import time
from datetime import datetime

from psycopg2.extras import execute_values
from psycopg2 import extensions as pg_ext
pg_ext.register_adapter(uuid.UUID, lambda val: pg_ext.AsIs(str(val)))
from pipeline.config import get_db_connection

# ── 48 Official Cambodia CPI 2018 Classes ──────────────────────
OFFICIAL_CLASSES: dict[str, str] = {
    "01.1.1": "Bread and cereals (Rice, flour, noodles, bread, baby cereal)",
    "01.1.2": "Meat (Beef, pork, poultry, duck)",
    "01.1.3": "Fish and seafood (Fresh, dried, processed fish, shrimp, crab)",    "01.1.4": "Milk, cheese and eggs (Dairy, fresh milk, infant formula milk)",
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
    "04.1.1": "Actual rentals paid by tenants",
    "04.3.1": "Materials for the maintenance and repair of the dwelling",
    "04.4.1": "Water supply",
    "04.5.1": "Electricity",
    "04.5.2": "Gas",
    "04.5.4": "Solid fuels",
    "05.1.1": "Furniture and furnishings",
    "05.2.1": "Household textiles",
    "05.5.1": "Glassware, tableware and household utensils",
    "05.6.1": "Non-durable household goods",
    "06.1.1": "Pharmaceutical products",
    "06.1.2": "Other medical products",
    "06.2.1": "Medical services",
    "07.1.2": "Motorcycles",
    "07.2.2": "Fuels and lubricants",
    "07.2.3": "Maintenance and repair of personal transport",
    "07.3.2": "Passenger transport by bus, coach and van",
    "08.2.0": "Telephone equipment",
    "08.3.0": "Telephone and internet services",
    "09.1.1": "Equipment for reception/recording of sound and pictures",
    "09.1.3": "Information processing equipment",
    "09.3.1": "Games, toys and hobbies",
    "09.5.1": "Books and stationery",
    "10.1.0": "Education services",
    "11.1.1": "Restaurants, cafes and the like",
    "11.2.0": "Accommodation services",
    "12.1.1": "Hairdressing salons and personal grooming",
    "12.1.3": "Personal care products",
    "12.3.1": "Jewellery, clocks and watches",
    "12.3.2": "Other personal effects",
}

PURE_STORE_MAP: dict[str, tuple[str, str]] = {
    "new_gasoline": ("07", "07.2.2"),
    "cellcard": ("08", "08.3.0"),
    "cellcard_wifi": ("08", "08.3.0"),
    "smart": ("08", "08.3.0"),
    "smart_wifi": ("08", "08.3.0"),
    "metfone": ("08", "08.3.0"),
    "realestate": ("04", "04.1.1"),
    "khmer24": ("04", "04.1.1"),
    "edc": ("04", "04.5.1"),
    "ppwsa": ("04", "04.4.1"),
    "redbus": ("07", "07.3.2"),
    "bookmebus": ("07", "07.3.2"),
    "khmermoto": ("07", "07.1.2"),
    "sokhahotel": ("11", "11.2.0"),
    "hyyathotel": ("11", "11.2.0"),
    "bayonbkk": ("11", "11.1.1"),
    "samnangshop": ("08", "08.2.0"),
    "arystore": ("08", "08.2.0"),
}

SUPERMARKET_STORES = {"aeon", "aeon3", "delishop", "grab_lucky", "grab_chipmong", "l192"}

DEFAULT_CODE = "01.1.9"

def classify_by_store_and_name(name_clean: str, store_slug: str) -> tuple[str, str, float, str]:
    """Pure rules-based classification."""
    name_lower = (name_clean or "").lower().strip()
    store = store_slug.lower().strip() if store_slug else ""

    # Tier 1: Pure store domains
    if store in PURE_STORE_MAP:
        div, code = PURE_STORE_MAP[store]
        return div, code, 1.0, f"pure_store_{store}"

    # Tier 2: Supermarket grocery overrides
    if store in SUPERMARKET_STORES:
        for kw, c in [
            ("chicken", "01.1.2"), ("pork", "01.1.2"), ("beef", "01.1.2"), ("duck", "01.1.2"),
            ("meat", "01.1.2"), ("sausage", "01.1.2"), ("fish", "01.1.3"), ("shrimp", "01.1.3"),
            ("seafood", "01.1.3"), ("salmon", "01.1.3"), ("tuna", "01.1.3"),
            ("bread", "01.1.1"), ("bakery", "01.1.1"), ("noodle", "01.1.1"), ("pasta", "01.1.1"),
            ("rice", "01.1.1"), ("flour", "01.1.1"),
            ("coffee", "01.2.1"), ("tea", "01.2.1"), ("cocoa", "01.2.1"),
            ("juice", "01.2.2"), ("water", "01.2.2"), ("soda", "01.2.2"), ("drink", "01.2.2"),
            ("vegetable", "01.1.7"), ("potato", "01.1.7"), ("fruit", "01.1.6"),
            ("oil", "01.1.5"), ("sugar", "01.1.8"), ("salt", "01.1.9"),
            ("chocolate", "01.1.8"), ("cookie", "01.1.8"), ("snack", "01.1.8"),
            ("candy", "01.1.8"), ("honey", "01.1.8"), ("jam", "01.1.8"),
            ("cheese", "01.1.4"), ("egg", "01.1.4"), ("milk", "01.1.4"),
            ("dairy", "01.1.4"), ("butter", "01.1.5"),
            ("soy sauce", "01.1.9"), ("fish sauce", "01.1.9"), ("sauce", "01.1.9"),
            ("spice", "01.1.9"), ("broth", "01.1.9"), ("soup", "01.1.9"),
            ("vinegar", "01.1.9"), ("condiment", "01.1.9"),
        ]:
            if kw in name_lower:
                return _div_from_code(c), c, 0.95, f"supermarket_keyword_{kw}"
        return "01", "01.1.9", 0.85, "supermarket_default"

    # Tier 3: Keyword matching
    for kw, c in [
        ("motorcycle", "07.1.2"), ("motorbike", "07.1.2"), ("scooter", "07.1.2"),
        ("gasoline", "07.2.2"), ("fuel", "07.2.2"), ("diesel", "07.2.2"), ("petrol", "07.2.2"),
        ("lpg", "04.5.2"), ("gas cylinder", "04.5.2"),
        ("phone", "08.2.0"), ("charger", "08.2.0"), ("screen protector", "08.2.0"),
        ("case", "08.2.0"), ("accessory", "08.2.0"), ("power bank", "08.2.0"),
        ("sim", "08.3.0"), ("data", "08.3.0"), ("internet", "08.3.0"), ("broadband", "08.3.0"),
        ("tv", "09.1.1"), ("audio", "09.1.1"), ("speaker", "09.1.1"),
        ("laptop", "09.1.3"), ("pc", "09.1.3"), ("computer", "09.1.3"), ("tablet", "09.1.3"),
        ("toy", "09.3.1"), ("game", "09.3.1"), ("sports", "09.3.1"), ("fitness", "09.3.1"),
        ("yoga", "09.3.1"), ("camping", "09.3.1"), ("bicycle", "09.3.1"),
        ("book", "09.5.1"), ("notebook", "09.5.1"), ("pen", "09.5.1"), ("pencil", "09.5.1"),
        ("ruler", "09.5.1"), ("stationery", "09.5.1"), ("eraser", "09.5.1"),
        ("tuition", "10.1.0"), ("education", "10.1.0"),
        ("restaurant", "11.1.1"), ("dining", "11.1.1"), ("cafe", "11.1.1"), ("food", "11.1.1"),
        ("hotel", "11.2.0"), ("accommodation", "11.2.0"),
        ("haircut", "12.1.1"), ("salon", "12.1.1"), ("barber", "12.1.1"),
        ("toothpaste", "12.1.3"), ("soap", "12.1.3"), ("shampoo", "12.1.3"), ("cosmetic", "12.1.3"),
        ("perfume", "12.1.3"), ("skincare", "12.1.3"), ("cream", "12.1.3"),
        ("diaper", "12.1.3"), ("wipe", "12.1.3"), ("pampers", "12.1.3"),
        ("shoe", "03.2.1"), ("slipper", "03.2.1"), ("sandal", "03.2.1"), ("boot", "03.2.1"),
        ("shirt", "03.1.2"), ("pant", "03.1.2"), ("dress", "03.1.2"), ("cloth", "03.1.2"),
        ("jacket", "03.1.2"), ("coat", "03.1.2"), ("underwear", "03.1.2"), ("sock", "03.1.2"),
        ("jewellery", "12.3.1"), ("watch", "12.3.1"), ("ring", "12.3.1"), ("necklace", "12.3.1"),
        ("bottle", "05.5.1"), ("glass", "05.5.1"), ("cup", "05.5.1"), ("pot", "05.5.1"), ("pan", "05.5.1"),
        ("plate", "05.5.1"), ("fork", "05.5.1"), ("spoon", "05.5.1"), ("knife", "05.5.1"),
        ("chair", "05.1.1"), ("table", "05.1.1"), ("bed", "05.1.1"), ("sofa", "05.1.1"),
        ("bedsheet", "05.2.1"), ("blanket", "05.2.1"), ("towel", "05.2.1"),
        ("detergent", "05.6.1"), ("cleaner", "05.6.1"), ("paper", "05.6.1"), ("candle", "05.6.1"),
        ("medicine", "06.1.1"), ("drug", "06.1.1"), ("pill", "06.1.1"), ("vitamin", "06.1.1"),
        ("bandage", "06.1.2"), ("thermometer", "06.1.2"),
        ("fan", "04.5.1"), ("electric", "04.5.1"), ("bulb", "04.5.1"),
        ("firewood", "04.5.4"), ("charcoal", "04.5.4"),
        ("paint", "04.3.1"), ("tool", "04.3.1"), ("repair", "04.3.1"),
        ("bag", "03.1.3"), ("luggage", "03.1.3"), ("wallet", "03.1.3"), ("purse", "03.1.3"),
    ]:
        if kw in name_lower:
            return _div_from_code(c), c, 0.90, f"keyword_{kw}"

    # Default fallback
    return "01", DEFAULT_CODE, 0.50, "default_fallback"

def _div_from_code(code: str) -> str:
    return code.split(".")[0] if code else "01"

def load_new_items(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (csp.item_id)
            csp.item_id, csp.name_clean, csp.store_slug, csp.barcode,
            csp.coicop_code as current_code, csp.coicop_method as current_method
        FROM silver.clean_store_prices csp
        WHERE csp.item_id NOT IN (SELECT CAST(item_id AS text) FROM silver.canonical_items)
        AND csp.name_clean IS NOT NULL
        ORDER BY csp.item_id
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def commit_batch(cur, conn, items: list, model_name: str = "local_rules"):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S+00:00')
    insert_data = []
    cache_data = []
    for item in items:
        name = item["name_clean"]
        store = item["store_slug"]
        div, code, conf, reasoning = classify_by_store_and_name(name, store)
        item_id = str(uuid.UUID(item["item_id"])) if isinstance(item["item_id"], uuid.UUID) else item["item_id"]
        insert_data.append((item_id, name, "local_rules", div, code, conf, now_str))
        cache_data.append((name, code, conf, reasoning, model_name))

    if insert_data:
        execute_values(cur, """
            INSERT INTO silver.canonical_items
                (item_id, canonical_name, coicop_method, coicop_division, coicop_code, coicop_confidence, coicop_classified_at)
            VALUES %s
            ON CONFLICT (item_id) DO NOTHING;
        """, insert_data, page_size=2000)
    return len(insert_data)

def main():
    parser = argparse.ArgumentParser(description="Rules-based local classification")
    parser.add_argument("--execute", action="store_true", help="Commit to PostgreSQL")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    log = logging.getLogger("classify_local")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    items = load_new_items(conn)
    log.info("Total new items to classify: %d", len(items))

    batches = [items[i:i + args.batch_size] for i in range(0, len(items), args.batch_size)]
    log.info("Formed %d batches. Classifying with local rules...", len(batches))

    start = time.time()
    total_committed = 0
    for i, batch in enumerate(batches):
        if args.execute:
            committed = commit_batch(cur, conn, batch)
            total_committed += committed
            if (i + 1) % 10 == 0:
                conn.commit()
                log.info("Checkpoint: %d/%d batches, %d committed", i + 1, len(batches), total_committed)
        time.sleep(args.delay)

    if args.execute:
        conn.commit()
        # Sync clean_store_prices
        cur.execute("""
            UPDATE silver.clean_store_prices s
            SET coicop_division = ci.coicop_division, coicop_code = ci.coicop_code,
                coicop_method = ci.coicop_method, coicop_confidence = ci.coicop_confidence
            FROM silver.canonical_items ci
            WHERE s.item_id::text = ci.item_id::text
              AND ci.coicop_method = 'local_rules'
              AND (s.coicop_division IS DISTINCT FROM ci.coicop_division OR s.coicop_code IS DISTINCT FROM ci.coicop_code);
        """)
        synced = cur.rowcount
        conn.commit()
        log.info("Synchronized %d observations in clean_store_prices.", synced)

    cur.execute("SELECT COUNT(*) FROM silver.canonical_items")
    total = cur.fetchone()[0]
    elapsed = time.time() - start
    rate = len(items) / elapsed if elapsed > 0 else 0
    log.info("Total canonical_items: %d", total)
    log.info("Classification complete in %.1fs (%.1f items/s)", elapsed, rate)
    conn.close()

if __name__ == "__main__":
    main()
