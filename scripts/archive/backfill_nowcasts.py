"""
scripts/backfill_nowcasts.py
────────────────────────────
Recomputes daily nowcasts in gold.fct_cpi_nowcast across all available daily scraped facts
(2026-08-17 to 2026-09-18) using the 36-month calibrated 5-basket Ridge model,
and cleans up any legacy model records.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import pandas as pd

# Ensure UTF-8 output on Windows / Linux
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

if "CPI_DATABASE_URL" not in os.environ:
    os.environ["CPI_DATABASE_URL"] = "postgresql://cpi_user:cpi_pass@postgres:5432/cpi_db"

from ml.nowcaster import CPINowcaster
from pipeline.config import get_db_connection


def main():
    print("=" * 75)
    print("CAMBODIA CPI PIPELINE: 5-BASKET RIDGE HISTORICAL NOWCAST BACKFILL")
    print("=" * 75)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Clean up legacy model records to ensure a unified time series
            print("[*] Removing legacy model records (ml_assisted_nowcaster_v1, hybrid_adl_gbrt_v1)...")
            cur.execute("DELETE FROM gold.fct_cpi_nowcast WHERE model_name != 'hybrid_ridge_5basket_v1';")
            deleted_nowcasts = cur.rowcount
            cur.execute("DELETE FROM gold.nowcast_performance_metrics WHERE model_name != 'hybrid_ridge_5basket_v1';")
            deleted_metrics = cur.rowcount
            conn.commit()
            print(f"[+] Cleaned up {deleted_nowcasts} legacy nowcasts and {deleted_metrics} legacy metrics.")

            # 2. Query all available daily calculation dates
            cur.execute(
                """
                SELECT DISTINCT calculation_date 
                FROM gold.fct_cpi_daily 
                WHERE calculation_date >= '2026-08-17' 
                ORDER BY calculation_date ASC;
                """
            )
            dates = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    if not dates:
        print("[-] No daily facts found in gold.fct_cpi_daily.")
        return

    nowcaster = CPINowcaster()
    last_date = pd.to_datetime(dates[-1]).date()

    print(f"[*] Starting backfill for {len(dates)} dates: {dates[0]} to {dates[-1]}")
    print("-" * 75)

    for i, d in enumerate(dates, 1):
        calc_date = pd.to_datetime(d).date()
        out = nowcaster.run_daily_nowcast(calc_date)
        print(
            f"[{i:02d}/{len(dates):02d}] {calc_date} | "
            f"Headline: {out['nowcast_headline_cpi']:.4f} | "
            f"MoM: {out['projected_mom_pct']:+.4f}% | "
            f"NIS: {out.get('nowcast_nis_headline_cpi', 0.0):.3f} | "
            f"Food: {out.get('nowcast_food_cpi', 0.0):.3f} | "
            f"Trans: {out.get('nowcast_transport_cpi', 0.0):.3f}"
        )

    print("-" * 75)
    print("[*] Updating out-of-sample performance evaluation tracking against NIS actuals...")
    metrics = nowcaster.persist_performance_metrics(last_date)
    print(f"[+] Successfully refreshed {len(metrics)} performance metric records!")
    print("=" * 75)
    print("✅ Complete historical nowcast backfill finished successfully!")
    print("=" * 75)


if __name__ == "__main__":
    main()
