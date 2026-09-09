"""
scripts/full_historical_cpi_backfill.py
───────────────────────────────────────
Full 23-Day Historical CPI Backfill Engine:
1. Synchronizes silver.clean_store_prices and gold.dim_items with high-confidence
   AI cache classifications (>= 0.70 confidence), eliminating legacy sinkhole assignments.
2. Recalculates gold.fct_elementary_indices and gold.fct_cpi_daily across all 23 historical
   dates using CPICalculationEngine with:
   - Subclass-first ILO class-mean imputation
   - Unclassified subclass protection (no 01.1.1 sinkhole)
3. Refreshes gold.fct_coicop_class_daily across all dates.
4. Conforms monthly CPI facts in gold.fct_cpi_monthly.
"""

import sys
import os
import time
from datetime import date, timedelta
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from pipeline.config import get_db_connection
from pipeline.cpi_calculator import CPICalculationEngine


def run_full_backfill():
    start_time = time.time()
    print("=" * 70)
    print("STARTING FULL 23-DAY HISTORICAL CPI RECLASSIFICATION & BACKFILL")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # STEP 1: Synchronize Silver & Gold Classifications from AI Cache
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Synchronizing Silver and Gold tables with AI Cache...")
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        t0 = time.time()
        # Update silver.clean_store_prices
        cur.execute(r"""
            UPDATE silver.clean_store_prices s
            SET coicop_division = CASE
                    WHEN split_part(ai.coicop_code, '.', 1) IN ('12', '13') THEN '12'
                    ELSE LPAD(split_part(ai.coicop_code, '.', 1), 2, '0')
                END,
                coicop_code = ai.coicop_code,
                coicop_method = 'gemini_ai_backfill',
                coicop_confidence = ai.confidence_score
            FROM (
                SELECT DISTINCT ON (lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')))
                    lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')) AS norm_name,
                    coicop_code,
                    confidence_score
                FROM silver.dim_coicop_ai_cache
                WHERE confidence_score >= 0.70
                  AND coicop_code <> '99.9.9'
                ORDER BY lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')), confidence_score DESC, classified_at DESC
            ) ai
            WHERE lower(regexp_replace(trim(s.name_clean), '\s+', ' ', 'g')) = ai.norm_name
              AND s.coicop_code <> ai.coicop_code;
        """)
        silver_updated = cur.rowcount
        print(f"   Updated {silver_updated:,} rows in silver.clean_store_prices in {time.time() - t0:.2f}s.")

        t0 = time.time()
        # Update gold.dim_items
        cur.execute(r"""
            UPDATE gold.dim_items d
            SET coicop_division = CASE
                    WHEN split_part(ai.coicop_code, '.', 1) IN ('12', '13') THEN '12'
                    ELSE LPAD(split_part(ai.coicop_code, '.', 1), 2, '0')
                END,
                coicop_code = ai.coicop_code
            FROM (
                SELECT DISTINCT ON (lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')))
                    lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')) AS norm_name,
                    coicop_code,
                    confidence_score
                FROM silver.dim_coicop_ai_cache
                WHERE confidence_score >= 0.70
                  AND coicop_code <> '99.9.9'
                ORDER BY lower(regexp_replace(trim(product_name), '\s+', ' ', 'g')), confidence_score DESC, classified_at DESC
            ) ai
            WHERE lower(regexp_replace(trim(d.canonical_name), '\s+', ' ', 'g')) = ai.norm_name
              AND d.coicop_code <> ai.coicop_code;
        """)
        gold_dim_updated = cur.rowcount
        print(f"   Updated {gold_dim_updated:,} canonical items in gold.dim_items in {time.time() - t0:.2f}s.")

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error during Step 1 synchronization: {e}")
        raise
    finally:
        conn.close()

    # -------------------------------------------------------------------------
    # STEP 2: Execute Daily CPI Calculation Loop Across All Dates
    # -------------------------------------------------------------------------
    print("\n[STEP 2] Re-running Econometric Calculation Engine across all dates...")
    engine = CPICalculationEngine()

    conn = engine.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT scrape_date 
                FROM silver.clean_store_prices 
                WHERE price_khr > 0 AND item_id IS NOT NULL 
                ORDER BY scrape_date ASC;
            """)
            dates = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    if not dates:
        print("No scrape dates found!")
        return

    base_date = dates[0] # Earliest available: 2026-08-18
    min_date = dates[0]
    max_date = dates[-1]
    print(f"   Target date range: {min_date} to {max_date} ({len(dates)} dates). Base date: {base_date}")

    load_start = min_date - timedelta(days=10)
    print(f"   Pre-loading clean store prices ({load_start} to {max_date})...")
    t0 = time.time()
    df_all = engine.load_clean_prices(load_start, max_date)
    print(f"   Loaded {len(df_all):,} price quotes in {time.time() - t0:.2f}s.")

    print(f"   Computing baseline reference prices for {base_date}...")
    t0 = time.time()
    base_df = engine.compute_base_prices(base_date, df_all)
    print(f"   Base basket established: {len(base_df):,} canonical items in {time.time() - t0:.2f}s.")

    # Loop over all target dates
    for idx, target_date in enumerate(dates, 1):
        day_t0 = time.time()
        history_start = target_date - timedelta(days=9)
        df_history = df_all[(df_all["scrape_date"] >= history_start) & (df_all["scrape_date"] <= target_date)]

        elementary_df = engine.compute_daily_elementary_indices(target_date, base_df, df_history)
        df_div, headline = engine.aggregate_division_and_headline(elementary_df, target_date, splice_factor=1.0)
        engine._save_to_database(elementary_df, df_div, headline)

        print(
            f"   [{idx:02d}/{len(dates):02d}] {target_date}: "
            f"Headline CPI={headline['headline_cpi']:.4f} | Core CPI={headline['core_cpi']:.4f} | "
            f"Items={headline['total_items']:,} ({time.time() - day_t0:.2f}s)"
        )

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
    print(f"FULL HISTORICAL BACKFILL COMPLETED SUCCESSFULLY IN {total_elapsed:.2f}s ({total_elapsed / 60:.2f} min)!")
    print("=" * 70)


if __name__ == "__main__":
    run_full_backfill()
