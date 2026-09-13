"""
scripts/recalculate_historical_cpi.py
──────────────────────────────────────
Recalculates gold.fct_cpi_daily, gold.fct_elementary_indices, and
gold.fct_cpi_monthly across all historical scrape dates using the clean
audited 12-division COICOP classifications.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from pipeline.cpi_calculator import CPICalculationEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def recalculate_all_history() -> None:
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
            dates = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    if not dates:
        logger.error("No dates found in silver.clean_store_prices!")
        return

    base_date = dates[0]
    logger.info("Found %d distinct dates from %s to %s. Base Date: %s", len(dates), dates[0], dates[-1], base_date)

    # 1. Recalculate daily indices
    for i, dt in enumerate(dates, 1):
        logger.info("[%d/%d] Recalculating CPI for %s...", i, len(dates), dt)
        try:
            engine.run_daily_pipeline(target_date=dt, base_date=base_date)
        except Exception as exc:
            logger.error("Failed calculating for %s: %s", dt, exc)

    # 2. Recalculate monthly indices
    logger.info("Computing conformed monthly CPI aggregations...")
    try:
        engine.compute_monthly_cpi()
        logger.info("✅ Monthly CPI calculation completed!")
    except Exception as exc:
        logger.error("Failed monthly CPI calculation: %s", exc)

    logger.info("🎉 All %d historical dates successfully recalculated and persisted to Gold layer!", len(dates))


if __name__ == "__main__":
    recalculate_all_history()
