"""
scripts/backfill_nowcasts.py
────────────────────────────
Recomputes daily nowcasts in gold.fct_cpi_nowcast across September 2026
using the reconciled historical CPI series.
"""
import sys
from datetime import date
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from ml.nowcaster import CPINowcaster

def main():
    print("=" * 60)
    print("BACKFILLING SEPTEMBER 2026 DAILY INFLATION NOWCASTS")
    print("=" * 60)
    nowcaster = CPINowcaster()
    for day in range(1, 10):
        d = date(2026, 9, day)
        out = nowcaster.run_daily_nowcast(d)
        print(f"[{d}] Nowcast Headline: {out['nowcast_headline_cpi']} | MoM: {out['projected_mom_pct']}% | CI: [{out['ci_lower_95']} - {out['ci_upper_95']}]")

if __name__ == "__main__":
    main()
