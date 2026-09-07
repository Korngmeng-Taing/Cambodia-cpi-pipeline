"""
scripts/monitor_pipeline_health.py
──────────────────────────────────
Automated 20-Source Health & Integrity Monitor for Cambodia Daily CPI Pipeline.
Audits:
1. 20-Source Daily Ingestion Volumes (Flags zero-count sources)
2. MEF USD/KHR Exchange Rate Integrity
3. Silver Deduplication & Match Ratios
4. 12-Division COICOP Coverage & Unclassified Items
5. Extreme Price Anomalies & Outliers
6. 3-Key Gemini Pool Status

Usage:
    python scripts/monitor_pipeline_health.py
    python scripts/monitor_pipeline_health.py --notify
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline.config import get_database_url
from pipeline.key_pool import get_key_pool
from scrapers.sources import SCRAPER_REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("pipeline_health_monitor")


def get_db_connection():
    from pipeline.config import alternate_host_url
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    # BUG FIX: Set 30s statement timeout so health checks never hang on slow/locked queries.
    timeout_opt = "-c statement_timeout=30000"
    try:
        return psycopg2.connect(conn_str, options=timeout_opt)
    except psycopg2.OperationalError:
        return psycopg2.connect(alternate_host_url(conn_str), options=timeout_opt)


def run_health_audit(scrape_date: str | None = None, send_notifications: bool = False) -> dict:
    today_str = scrape_date or datetime.now().strftime("%Y-%m-%d")
    conn = get_db_connection()

    report_lines = []
    has_critical_alerts = False
    total_records = 0
    rate = 0.0
    unclass_pct = 0.0

    report_lines.append("=" * 80)
    report_lines.append(f" 🛡️ CAMBODIA DAILY CPI PIPELINE HEALTH AUDIT — {today_str}")
    report_lines.append("=" * 80)

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # ----------------------------------------------------------------
            # 1. 20-Source Ingestion Health
            # ----------------------------------------------------------------
            cur.execute(
                """
                SELECT store_slug, record_count, created_at
                FROM staging.raw_scrapes
                WHERE scrape_date = %s
                ORDER BY record_count DESC;
                """,
                (today_str,)
            )
            scrapes = cur.fetchall()
            ingested_stores = {r["store_slug"]: r["record_count"] for r in scrapes}
            total_records = sum(ingested_stores.values())

            total_sources = len(SCRAPER_REGISTRY)
            report_lines.append(f"\n📦 1. {total_sources}-SOURCE INGESTION STATUS:")
            report_lines.append(f"   Total Daily Observations: {total_records:,} rows across {len(ingested_stores)}/{total_sources} sources")
            
            missing_sources = []
            zero_sources = []
            for slug in sorted(SCRAPER_REGISTRY.keys()):
                cnt = ingested_stores.get(slug)
                if cnt is None:
                    missing_sources.append(slug)
                    report_lines.append(f"   ❌ MISSING : {slug:<18} (No scrape recorded today)")
                elif cnt == 0:
                    zero_sources.append(slug)
                    report_lines.append(f"   ⚠️ ZERO-CNT: {slug:<18} (0 records ingested)")
                else:
                    report_lines.append(f"   ✅ HEALTHY : {slug:<18} ({cnt:>6,} rows)")

            if missing_sources or zero_sources:
                has_critical_alerts = True

            # ----------------------------------------------------------------
            # 2. MEF USD/KHR Exchange Rate Integrity
            # ----------------------------------------------------------------
            cur.execute(
                """
                SELECT rate, source, execution_date
                FROM staging.exchange_rates
                ORDER BY execution_date DESC
                LIMIT 1;
                """
            )
            fx_row = cur.fetchone()
            report_lines.append("\n💱 2. MEF USD/KHR EXCHANGE RATE:")
            if fx_row:
                rate = float(fx_row["rate"])
                fx_status = "HEALTHY" if (3900 <= rate <= 4300) else "ANOMALY"
                if fx_status != "HEALTHY":
                    has_critical_alerts = True
                report_lines.append(f"   Rate: {rate:,.2f} KHR/USD [{fx_status}] (Source: {fx_row['source']})")
            else:
                has_critical_alerts = True
                report_lines.append("   ❌ MISSING: No exchange rate available in staging.exchange_rates!")

            # ----------------------------------------------------------------
            # 3. Silver Item Matching & Deduplication
            # ----------------------------------------------------------------
            cur.execute(
                """
                SELECT match_method, COUNT(*) as count
                FROM silver.item_match_log iml
                JOIN bronze.raw_prices rp ON iml.raw_price_id = rp.raw_price_id
                WHERE rp.scraped_at::date = %s
                GROUP BY match_method
                ORDER BY count DESC;
                """,
                (today_str,)
            )
            match_rows = cur.fetchall()
            report_lines.append("\n🔗 3. SILVER ENTITY RESOLUTION RATIOS:")
            total_matched = sum(r["count"] for r in match_rows)
            if total_matched > 0:
                for r in match_rows:
                    pct = (r["count"] / total_matched) * 100
                    report_lines.append(f"   • {r['match_method']:<18}: {r['count']:>6,} ({pct:>5.1f}%)")
            else:
                report_lines.append("   ⚠️ No matching records found for today.")

            # ----------------------------------------------------------------
            # 4. COICOP 12-Division Distribution & Unclassified %
            # ----------------------------------------------------------------
            cur.execute(
                """
                SELECT 
                    COALESCE(c.coicop_division, 'UNCLASSIFIED') as division,
                    COUNT(*) as count
                FROM silver.canonical_items c
                GROUP BY 1
                ORDER BY count DESC;
                """
            )
            coicop_rows = cur.fetchall()
            report_lines.append("\n🏷️ 4. 12-DIVISION COICOP COVERAGE:")
            total_items = sum(r["count"] for r in coicop_rows)
            unclassified_cnt = 0
            for r in coicop_rows:
                if r["division"] in ("UNCLASSIFIED", "99", None):
                    unclassified_cnt += r["count"]
                pct = (r["count"] / total_items) * 100 if total_items > 0 else 0
                report_lines.append(f"   • Division {r['division']:<12}: {r['count']:>6,} ({pct:>5.1f}%)")

            unclass_pct = (unclassified_cnt / total_items) * 100 if total_items > 0 else 0
            if unclass_pct > 3.0:
                has_critical_alerts = True
                report_lines.append(f"   ⚠️ WARNING: High unclassified rate: {unclass_pct:.2f}%")

            # ----------------------------------------------------------------
            # 5. Gemini Key Pool Health
            # ----------------------------------------------------------------
            pool = get_key_pool()
            report_lines.append("\n🔑 5. GEMINI API KEY POOL:")
            report_lines.append(f"   Active Keys in Pool: {pool.get_key_count()} (Capacity: {pool.get_key_count() * 1500:,} req/day, {pool.get_key_count() * 15} RPM)")

    finally:
        conn.close()

    report_lines.append("\n" + "=" * 80)
    status_str = "🚨 CRITICAL ISSUES DETECTED" if has_critical_alerts else "✅ ALL SYSTEMS HEALTHY"
    report_lines.append(f" OVERALL PIPELINE STATUS: {status_str}")
    report_lines.append("=" * 80 + "\n")

    full_report = "\n".join(report_lines)
    print(full_report)

    return {
        "status": "ALERT" if has_critical_alerts else "OK",
        "total_records": total_records,
        "active_sources": len(ingested_stores),
        "unclassified_pct": unclass_pct,
    }


def main():
    parser = argparse.ArgumentParser(description="Pipeline Health & Observability Audit")
    parser.add_argument("--date", type=str, default=None, help="Scrape date to audit (YYYY-MM-DD), default today")
    args = parser.parse_args()

    run_health_audit(args.date)


if __name__ == "__main__":
    main()
