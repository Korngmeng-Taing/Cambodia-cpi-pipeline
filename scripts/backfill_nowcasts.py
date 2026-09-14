"""
scripts/backfill_nowcasts.py
────────────────────────────
Recomputes daily nowcasts in gold.fct_cpi_nowcast across September 2026
using the reconciled historical CPI series and 5-basket Ridge model.
"""
import os
import sys
from datetime import date
from pathlib import Path
import pandas as pd

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure rapid local resolution on host machine
if "CPI_DATABASE_URL" not in os.environ:
    os.environ["CPI_DATABASE_URL"] = "postgresql://cpi_user:cpi_pass@localhost:5432/cpi_db"

from ml.nowcaster import CPINowcaster
from pipeline.config import get_db_connection

def main():
    print("=" * 70)
    print("BACKFILLING SEPTEMBER 2026 DAILY INFLATION NOWCASTS (5-BASKET RIDGE)")
    print("=" * 70)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT calculation_date 
                FROM gold.fct_cpi_daily 
                WHERE calculation_date >= '2026-09-01' 
                ORDER BY calculation_date ASC;
                """
            )
            dates = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    if not dates:
        print("[-] No September 2026 dates found in gold.fct_cpi_daily.")
        return

    nowcaster = CPINowcaster()
    last_date = pd.to_datetime(dates[-1]).date()
    
    print(f"[*] Found {len(dates)} dates to backfill ({dates[0]} to {dates[-1]}).")
    for d in dates:
        calc_date = pd.to_datetime(d).date()
        out = nowcaster.run_daily_nowcast(calc_date)
        print(
            f"  [{calc_date}] Headline: {out['nowcast_headline_cpi']:.4f} | "
            f"MoM: {out['projected_mom_pct']:+.4f}% | "
            f"Food: {out.get('nowcast_food_cpi', 0.0):.4f} | "
            f"Trans: {out.get('nowcast_transport_cpi', 0.0):.4f}"
        )

    print("[*] Updating out-of-sample performance evaluation tracking...")
    nowcaster.persist_performance_metrics(last_date)
    print("✅ Backfill and performance tracking successfully updated!")

if __name__ == "__main__":
    main()
