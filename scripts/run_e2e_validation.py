import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from datetime import date
from pipeline.cpi_calculator import CPICalculationEngine
from ml.nowcaster import execute_nowcasting_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

print("=== 1. RUNNING DAILY CPI PIPELINE WITH BASE REGISTRY ===")
calc = CPICalculationEngine()
target_dt = date(2026, 9, 18)
calc.run_daily_pipeline(target_date=target_dt)

print("\n=== 2. RUNNING HYBRID RIDGE NOWCASTING PIPELINE ===")
res = execute_nowcasting_pipeline(target_date=target_dt)
print(f"Nowcast Result: Headline = {res.get('nowcast_headline_cpi')}, Core = {res.get('nowcast_core_cpi')}")
print("\n=== SUCCESS: END-TO-END EXECUTION COMPLETE ===")
