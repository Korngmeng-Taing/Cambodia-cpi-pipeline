"""
=============================================================================
HISTORICAL CPI BACKTEST & DAILY CALCULATION RUNNER (Aug 18 to Aug 26)
=============================================================================
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, timedelta
from pipeline.cpi_calculator import CPICalculationEngine

def run_historical_cpi_backtest():
    start_date = date(2026, 8, 18)
    end_date = date(2026, 8, 26)
    base_date = date(2026, 8, 18)

    print("=" * 80)
    print(f" CAMBODIA CPI PIPELINE -- HISTORICAL INDEX BACKTEST ({start_date} -> {end_date})")
    print("=" * 80)

    engine = CPICalculationEngine()
    
    current = start_date
    while current <= end_date:
        print(f"\n Processing Date: {current} ...")
        engine.run_daily_pipeline(target_date=current, base_date=base_date)
        current += timedelta(days=1)

    print("\n" + "=" * 80)
    print(" HISTORICAL CPI BACKTEST SUCCESSFULLY COMPLETED FOR ALL DATES!")
    print("=" * 80)

if __name__ == "__main__":
    run_historical_cpi_backtest()
