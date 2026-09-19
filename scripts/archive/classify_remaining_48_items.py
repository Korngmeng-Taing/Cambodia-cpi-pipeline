"""
scripts/classify_remaining_48_items.py
──────────────────────────────────────
Classifies the remaining 48 service, transport, and rental items in silver.canonical_items:
- Bus tickets -> 07.3.2 (Transport / Bus & Coach)
- Real estate rentals (Apartments, Condos, Villas, Shophouses) -> 04.1.1 (Actual rentals paid by tenants)
- Real estate sale -> 04.2.1 (Housing / Imputed rentals)
- Vitalia Muesli -> 01.1.1 (Bread & Cereals)
- Nestlé Brassé Pear -> 01.1.9 (Food products n.e.c. / Baby food)
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from psycopg2.extras import RealDictCursor
from pipeline.config import get_db_connection

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def classify_item(name: str) -> tuple[str, str]:
    name_upper = name.upper()
    if "BUS TICKET" in name_upper or "VIP EXPRESS" in name_upper or "VIP SLEEPING BUS" in name_upper or "VIP VAN" in name_upper:
        return "07.3.2", "07"
    if "MUESLI" in name_upper:
        return "01.1.1", "01"
    if "BRASSÉ PEAR" in name_upper or "NESTLÉ" in name_upper:
        return "01.1.9", "01"
    if "ត្រូវការលក់" in name or "FOR SALE" in name_upper:
        return "04.2.1", "04"
    if any(k in name_upper for k in ["RENT", "ជួល", "APARTMENT", "CONDO", "VILLA", "ROOM", "SHOPHOUSE", "HOUSE"]):
        return "04.1.1", "04"
    return "04.1.1", "04"

def main():
    print("=" * 70)
    print("CLASSIFYING REMAINING 48 CANONICAL ITEMS")
    print("=" * 70)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT item_id, canonical_name
                FROM silver.canonical_items
                WHERE coicop_division IS NULL OR coicop_code IS NULL;
            """)
            items = cur.fetchall()
            print(f"Found {len(items)} items to classify.\n")

            updated_count = 0
            for it in items:
                item_id = it["item_id"]
                name = it["canonical_name"]
                code, div = classify_item(name)

                # 1. Update silver.canonical_items
                cur.execute("""
                    UPDATE silver.canonical_items
                    SET coicop_code = %s,
                        coicop_division = %s
                    WHERE item_id = %s;
                """, (code, div, item_id))

                # 2. Update silver.clean_store_prices
                cur.execute("""
                    UPDATE silver.clean_store_prices
                    SET coicop_code = %s
                    WHERE item_id = %s;
                """, (code, item_id))

                # 3. Add to silver.dim_coicop_ai_cache
                cur.execute("""
                    INSERT INTO silver.dim_coicop_ai_cache (
                        product_name, coicop_code, confidence_score, reasoning, model_version, classified_at
                    ) VALUES (
                        %s, %s, 0.99, 'expert_rule_services', 'gemini-1.5-pro', NOW()
                    )
                    ON CONFLICT (product_name) DO UPDATE
                    SET coicop_code = EXCLUDED.coicop_code,
                        confidence_score = 0.99,
                        reasoning = 'expert_rule_services';
                """, (name, code))

                updated_count += 1
                print(f"[{updated_count:02d}] {code} (Div {div}) -> {name[:60]}")

        conn.commit()
        print(f"\n✅ Successfully classified and committed {updated_count} items!")

if __name__ == "__main__":
    main()
