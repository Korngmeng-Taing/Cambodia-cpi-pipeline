"""
scripts/recalculate_gold.py
───────────────────────────
Recalculates all Gold Layer tables, procedures, and indices across all historical scrape dates.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))
import psycopg2
from pipeline.fisher_calculator import FisherCalculator
from pipeline.geks_calculator import GEKSCalculator

def main():
    conn = psycopg2.connect("postgresql://cpi_user:cpi_pass@localhost:5432/cpi_db")
    conn.autocommit = True
    cur = conn.cursor()

    print("[1/4] Bootstrapping Base Prices (August 2026 reference)...")
    cur.execute("CALL gold.sp_bootstrap_base_prices('2026-08');")

    print("[2/4] Fetching available dates from Silver facts...")
    cur.execute("SELECT DISTINCT scrape_date FROM silver.fct_daily_prices ORDER BY scrape_date ASC;")
    dates = [r[0].strftime("%Y-%m-%d") for r in cur.fetchall()]
    print(f"Found {len(dates)} dates to calculate: {dates}")

    fc = FisherCalculator()
    gc = GEKSCalculator()

    print("[3/4] Running Gold procedures and Superlative index calculators...")
    for d in dates:
        print(f"  -> Processing {d}...")
        cur.execute("CALL gold.sp_calculate_daily_cpi(%s::DATE, '2026-08');", (d,))
        fc.run_fisher_for_date(d, "2026-08")
        gc.run_rolling_geks_for_date(d, window_size=13, base_period="2026-08")

    print("[4/4] Validation Summary:")
    cur.execute("""
        SELECT 
            m.scrape_date,
            m.cpi_headline_khr,
            m.cpi_headline_usd,
            m.cpi_geks_multilateral,
            f.fisher_index,
            f.substitution_bias_pct,
            m.inflation_dod_pct,
            m.inflation_mom_pct,
            m.divisions_present,
            m.active_quotes_count
        FROM gold.mart_cpi_daily m
        LEFT JOIN gold.cpi_fisher_superlative f ON f.scrape_date = m.scrape_date
        ORDER BY m.scrape_date DESC;
    """)
    rows = cur.fetchall()
    print("\nDate       | Headline (KHR) | Headline (USD) | GEKS-Tornqvist | Fisher Index | Sub. Bias (pts) | DoD (%) | Active Quotes")
    print("------------------------------------------------------------------------------------------------------------------")
    for r in rows:
        print(f"{r[0]} | {r[1]:>14} | {r[2]:>14} | {str(r[3] or 'N/A'):>14} | {str(r[4] or 'N/A'):>12} | {str(r[5] or 'N/A'):>15} | {str(r[6] or 'N/A'):>7} | {r[9]:>13}")

    conn.close()
    print("\nGold recalculation finished successfully!")

if __name__ == "__main__":
    main()
