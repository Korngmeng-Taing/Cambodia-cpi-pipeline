"""
=============================================================================
BACKFILL GOLD CPI LAYER (2026-08-18 TO PRESENT)
Recalculates:
  1. gold.fct_elementary_indices
  2. gold.fct_cpi_daily
  3. gold.fct_cpi_monthly
Using 100% clean Silver classifications with zero mismatches and zero reviews.
=============================================================================
"""
import sys
import logging
from datetime import timedelta
from pathlib import Path
import time

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from pipeline.cpi_calculator import CPICalculationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("backfill_gold_cpi")


def run_backfill():
    start_total = time.time()
    engine = CPICalculationEngine()
    
    # 1. Determine all unique scrape dates available in silver.clean_store_prices
    log.info("Fetching available scrape dates from silver.clean_store_prices...")
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
        log.error("No valid scrape dates found in silver.clean_store_prices!")
        return

    base_date = dates[0] # Earliest date: 2026-08-18
    min_date = dates[0]
    max_date = dates[-1]
    log.info(f"📅 Target date range: {min_date} to {max_date} ({len(dates)} dates). Base date: {base_date}")

    # 2. Pre-load ALL clean store price observations across the entire range into memory
    # Load 10 days before min_date for imputation window
    load_start = min_date - timedelta(days=10)
    log.info(f"⏳ Pre-loading clean store prices from {load_start} to {max_date} into memory...")
    t0 = time.time()
    df_all = engine.load_clean_prices(load_start, max_date)
    log.info(f"✅ Loaded {len(df_all):,} rows in {time.time() - t0:.2f}s.")

    # 3. Compute base prices once
    log.info(f"🔧 Computing base prices for base date: {base_date}...")
    t0 = time.time()
    base_df = engine.compute_base_prices(base_date, df_all)
    log.info(f"✅ Base basket computed: {len(base_df):,} unique canonical items in {time.time() - t0:.2f}s.")

    # 4. Fetch chain-linking splice factor from gold.cpi_base_dates if available
    splice_factor = 1.0
    conn_splice = None
    try:
        conn_splice = engine.get_connection()
        with conn_splice.cursor() as cur:
            cur.execute("""
                SELECT avg_december_cpi 
                FROM gold.cpi_base_dates 
                WHERE effective_from <= %s 
                ORDER BY effective_from DESC 
                LIMIT 1;
            """, (max_date,))
            row = cur.fetchone()
            if row and row[0] is not None and float(row[0]) > 0:
                splice_factor = float(row[0]) / 100.0
                log.info(f"Applying chain-linking splice factor: {splice_factor:.4f}")
    except Exception as e:
        log.debug(f"Splice factor lookup skipped: {e}")
    finally:
        if conn_splice is not None:
            conn_splice.close()

    # 5. Loop over all target dates and calculate daily CPI
    log.info(f"🚀 Starting calculation loop across {len(dates)} dates...")
    for idx, target_date in enumerate(dates, 1):
        day_t0 = time.time()
        # Trailing imputation window (target_date - 9 days to target_date)
        history_start = target_date - timedelta(days=9)
        df_history = df_all[(df_all["scrape_date"] >= history_start) & (df_all["scrape_date"] <= target_date)]
        
        # Compute elementary indices with shadow tracking to prevent new item dilution
        elementary_df = engine.compute_daily_elementary_indices(
            target_date, base_df, df_history, shadow_track_new_items=True
        )
        
        # Aggregate division and headline CPI with invariant fixed-weight imputation
        df_div, headline = engine.aggregate_division_and_headline(
            elementary_df, target_date, splice_factor=splice_factor, impute_missing_divisions=True
        )
        
        # Save to database
        engine._save_to_database(elementary_df, df_div, headline)
        
        log.info(
            f"[{idx:02d}/{len(dates):02d}] {target_date}: "
            f"Headline={headline['headline_cpi']:.2f}, Core={headline['core_cpi']:.2f}, "
            f"Items={headline['total_items']:,} in {time.time() - day_t0:.2f}s"
        )

    # 6. Recompute and save monthly CPI facts
    log.info("📊 Recomputing monthly CPI facts for gold.fct_cpi_monthly...")
    monthly_df = engine.compute_monthly_cpi()
    engine.save_monthly_cpi(monthly_df)

    log.info(f"🎉 Complete Gold layer CPI backfill finished in {time.time() - start_total:.2f}s!")


if __name__ == "__main__":
    run_backfill()
