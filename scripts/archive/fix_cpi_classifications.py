"""
scripts/fix_cpi_classifications.py
──────────────────────────────────
Remediates misclassified items in silver.clean_store_prices, gold.dim_items,
and gold.fct_elementary_indices.
Updates dim_coicop_ai_cache, creates gold.v_cpi_micro_audit, and recalculates
CPI facts for 2026-08-18, 2026-09-07, 2026-09-08, 2026-09-09 using CPICalculationEngine.
"""

import sys
import os
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import get_db_connection
from pipeline.cpi_calculator import CPICalculationEngine

REMEDIATION_ITEMS = [
    {
        "item_id": "0158ba6d-e5fe-403f-bd0c-6f69a16ad89f",
        "name": "MG POP UP TISSUE 6PACKS",
        "division": "05",
        "code": "05.6.1",
        "reasoning": "Household cleaning / paper tissue non-durable goods"
    },
    {
        "item_id": "666c1c68-bc2b-4772-91db-522e5832dc01",
        "name": "HARIMAYA GREEN TEA (TEA BAG) 100`SX2G",
        "division": "01",
        "code": "01.2.1",
        "reasoning": "Green tea in tea bags"
    },
    {
        "item_id": "ece7a94f-ca6b-44b3-947b-20a512a4eb4e",
        "name": "STRAWBERRY DRINK - WICKY",
        "division": "01",
        "code": "01.2.2",
        "reasoning": "Fruit flavoured soft drink / beverage"
    },
    {
        "item_id": "7fb10c9d-7292-4312-a764-9a94e2ccac3e",
        "name": "MILK CHOCOLATE COATED COFFEE BEAN 48G",
        "division": "01",
        "code": "01.1.8",
        "reasoning": "Chocolate confectionery"
    },
    {
        "item_id": "1a7bca3c-de5c-4508-978f-096e994fc306",
        "name": "ZUCHINI GREEN (≈400G)",
        "division": "01",
        "code": "01.1.7",
        "reasoning": "Fresh zucchini vegetable"
    },
    {
        "item_id": "9a8b0725-7e2c-43eb-9230-60fc189fdb98",
        "name": "GRANULATED CHICKEN BOUILLON, 1KG",
        "division": "01",
        "code": "01.1.9",
        "reasoning": "Bouillon seasoning / condiment"
    }
]

def run_remediation():
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("1. Updating silver.dim_coicop_ai_cache...")
        for item in REMEDIATION_ITEMS:
            cur.execute("""
                INSERT INTO silver.dim_coicop_ai_cache (
                    product_name, coicop_code, confidence_score, reasoning, model_version, classified_at
                ) VALUES (%s, %s, 1.0000, %s, 'remediated_audit', NOW())
                ON CONFLICT (product_name) DO UPDATE
                SET coicop_code = EXCLUDED.coicop_code,
                    confidence_score = EXCLUDED.confidence_score,
                    reasoning = EXCLUDED.reasoning,
                    classified_at = NOW();
            """, (item["name"], item["code"], item["reasoning"]))

        print("2. Updating silver.clean_store_prices...")
        for item in REMEDIATION_ITEMS:
            cur.execute("""
                UPDATE silver.clean_store_prices
                SET coicop_division = %s,
                    coicop_code = %s,
                    coicop_method = 'audit_remediated',
                    coicop_confidence = 1.000
                WHERE item_id = %s;
            """, (item["division"], item["code"], item["item_id"]))

        print("3. Updating gold.dim_items...")
        for item in REMEDIATION_ITEMS:
            cur.execute("""
                UPDATE gold.dim_items
                SET coicop_division = %s,
                    coicop_code = %s
                WHERE item_id = %s;
            """, (item["division"], item["code"], item["item_id"]))

        print("4. Updating gold.fct_elementary_indices...")
        for item in REMEDIATION_ITEMS:
            cur.execute("""
                UPDATE gold.fct_elementary_indices
                SET coicop_division = %s,
                    coicop_code = %s
                WHERE item_id = %s;
            """, (item["division"], item["code"], item["item_id"]))

        print("5. Creating gold.v_cpi_micro_audit view...")
        cur.execute("""
            CREATE OR REPLACE VIEW gold.v_cpi_micro_audit AS
            SELECT 
                calculation_date,
                coicop_division,
                coicop_code,
                COUNT(*) AS total_items,
                COUNT(*) FILTER (WHERE is_imputed = FALSE AND elementary_index != 100.0) AS real_price_changes,
                COUNT(*) FILTER (WHERE is_imputed = TRUE) AS imputed_items,
                COUNT(*) FILTER (WHERE elementary_index = 100.0) AS unchanged_items,
                ROUND(AVG(elementary_index) FILTER (WHERE is_imputed = FALSE), 4) AS observed_elementary_index,
                ROUND(AVG(elementary_index), 4) AS composite_elementary_index
            FROM gold.fct_elementary_indices
            GROUP BY calculation_date, coicop_division, coicop_code;
        """)

        conn.commit()
        print(" Database remediation applied successfully!")
    except Exception as e:
        conn.rollback()
        print(f" Error during remediation: {e}")
        raise
    finally:
        conn.close()

    # Re-run CPI calculation engine for target dates to re-aggregate division and headline CPI
    print("6. Re-aggregating daily CPI facts using CPICalculationEngine...")
    engine = CPICalculationEngine()
    target_dates = [
        date(2026, 8, 18),
        date(2026, 9, 7),
        date(2026, 9, 8),
        date(2026, 9, 9)
    ]
    for d in target_dates:
        print(f"   Calculating CPI for {d}...")
        engine.run_daily_pipeline(target_date=d, base_date=date(2026, 8, 18))

    print(" All remediation and recalculation complete!")

if __name__ == "__main__":
    run_remediation()
