"""
scripts/finish_backfill_steps.py
────────────────────────────────
Completes Step 3 and Step 4 of the historical CPI backfill:
1. Refreshes gold.fct_coicop_class_daily across all 23 dates from gold.fct_elementary_indices.
2. Computes conformed monthly CPI facts in gold.fct_cpi_monthly.
"""
import sys
import os
import time
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from pipeline.cpi_calculator import CPICalculationEngine

def main():
    start_time = time.time()
    print("=" * 70)
    print("COMPLETING HISTORICAL CPI BACKFILL: STEPS 3 & 4")
    print("=" * 70)

    engine = CPICalculationEngine()

    # -------------------------------------------------------------------------
    # STEP 3: Refresh gold.fct_coicop_class_daily
    # -------------------------------------------------------------------------
    print("\n[STEP 3] Refreshing gold.fct_coicop_class_daily across all dates...")
    conn = engine.get_connection()
    try:
        with conn.cursor() as cur:
            t0 = time.time()
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_fct_coicop_class_daily
                ON gold.fct_coicop_class_daily (calculation_date, coicop_code);

                TRUNCATE TABLE gold.fct_coicop_class_daily;

                INSERT INTO gold.fct_coicop_class_daily (
                    calculation_date, coicop_division, coicop_code,
                    class_index, item_count, total_observations, imputed_item_count, created_at
                )
                SELECT
                    calculation_date,
                    coicop_division,
                    coicop_code,
                    ROUND((EXP(AVG(LN(price_ratio))) * 100.0)::numeric, 4) AS class_index,
                    COUNT(*) AS item_count,
                    SUM(observation_count) AS total_observations,
                    SUM(CASE WHEN is_imputed THEN 1 ELSE 0 END) AS imputed_item_count,
                    NOW() AS created_at
                FROM gold.fct_elementary_indices
                WHERE price_ratio > 0
                GROUP BY calculation_date, coicop_division, coicop_code;
            """)
            conn.commit()
            print(f"   Refreshed {cur.rowcount:,} subclass rows in gold.fct_coicop_class_daily in {time.time() - t0:.2f}s.")
    finally:
        conn.close()

    # -------------------------------------------------------------------------
    # STEP 4: Conformed Monthly CPI Aggregation
    # -------------------------------------------------------------------------
    print("\n[STEP 4] Computing conformed monthly CPI in gold.fct_cpi_monthly...")
    t0 = time.time()
    monthly_df = engine.compute_monthly_cpi()
    engine.save_monthly_cpi(monthly_df)
    print(f"   Monthly CPI facts successfully saved in {time.time() - t0:.2f}s.")

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"ALL STEPS COMPLETED SUCCESSFULLY IN {total_elapsed:.2f}s!")
    print("=" * 70)

if __name__ == "__main__":
    main()
