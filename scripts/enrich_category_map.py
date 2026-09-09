"""
scripts/enrich_category_map.py
──────────────────────────────
Enriches silver.coicop_category_map with taxonomy mappings for:
- Aeon 3 (Fashion, Beauty, Accessories)
- L192 (Apparel, Household Goods)
- Khmer24 (Residential Rentals)
- Community Pharma (Pharmaceuticals, Tablets)
- Ary Store (Smartphones, Accessories)
"""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from pipeline.config import get_db_connection

NEW_MAPPINGS = [
    # Aeon 3
    ("aeon3", "Fashion & Beauty", "03"),
    ("aeon3", "Beauty > Perfume", "12"),
    ("aeon3", "Shoes Bag & Accessories > Ladies Bags", "03"),
    ("aeon3", "Shoes Bag & Accessories", "03"),
    ("aeon3", "Ladies Wear", "03"),
    ("aeon3", "Men's Wear", "03"),
    ("aeon3", "Kids & Babies", "03"),
    ("aeon3", "Beauty", "12"),
    # L192
    ("l192", "General Retail > Apparel & Household Goods", "03"),
    ("l192", "Apparel & Household Goods", "03"),
    ("l192", "Women's Fashion", "03"),
    ("l192", "Men's Fashion", "03"),
    # Khmer24
    ("khmer24", "Residential Rental > House For Rent", "04"),
    ("khmer24", "Residential Rental > Room For Rent", "04"),
    ("khmer24", "Residential Rental > Apartment For Rent", "04"),
    ("khmer24", "Residential Rental > Land For Rent", "04"),
    ("khmer24", "Residential Rental", "04"),
    # Community Pharma
    ("communitypharma", "Pharmaceutical Products", "06"),
    ("communitypharma", "Tablet", "06"),
    ("communitypharma", "Capsule", "06"),
    ("communitypharma", "Syrup", "06"),
    ("communitypharma", "Medical Supplies", "06"),
    # Ary Store
    ("arystore", "Mobile / Samsung / Samsung / Smartphones", "08"),
    ("arystore", "Mobile / Smartphones / Vivo / Vivo", "08"),
    ("arystore", "Mobile / Oppo / Oppo / Smartphones", "08"),
    ("arystore", "Mobile / Smartphones / Tecno / Tecno", "08"),
    ("arystore", "Xiaomi / Mobile / Redmi / Smartphones / Xiaomi", "08"),
    ("arystore", "Case / Accessories / Nillkin / Phone Case", "08"),
    ("arystore", "Nillkin / Accessories / Case / Phone Case", "08"),
    ("arystore", "Accessory / Accessories / Apple / Phone Case", "08"),
    ("arystore", "Accessories / AirPods/Buds Case", "08"),
    ("arystore", "Watch / Huawei / Huawei Watches / Smartwatches", "08"),
    ("arystore", "Mobile", "08"),
    ("arystore", "Accessories", "08"),
]

def enrich_categories():
    print("=" * 60)
    print("ENRICHING SILVER.COICOP_CATEGORY_MAP")
    print("=" * 60)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            inserted = 0
            for store, cat, div in NEW_MAPPINGS:
                cur.execute("""
                    INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING;
                """, (store, cat, div))
                inserted += cur.rowcount

            conn.commit()
            print(f"Successfully inserted {inserted} new category mappings into silver.coicop_category_map!")

            cur.execute("SELECT COUNT(*) FROM silver.coicop_category_map;")
            total = cur.fetchone()[0]
            print(f"Total active category mappings in database: {total}")
    finally:
        conn.close()

if __name__ == "__main__":
    enrich_categories()
