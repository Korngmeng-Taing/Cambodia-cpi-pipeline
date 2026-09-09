"""
pipeline/bronze_ingestion.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Bronze ingestion entrypoint used by the per-source Airflow scraper DAGs.

Flow (adheres to SCRAPER_METHODOLOGY_GUIDE.md Â§1 & Â§3):
    fetch_records â”€â–º canonical.normalize_records (Schema v1.0)
      â”€â–º zero-product quality gate â”€â–º DQ validate
      â”€â–º PostgreSQL staging.raw_scrapes + bronze.raw_prices

The MEF USD/KHR exchange rate is routed separately to staging.exchange_rates.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from datetime import datetime

from pipeline.bronze_scraper import BronzeScraper
from pipeline.config import get_db_connection
from pipeline.canonical import normalize_records, validate_records
from scrapers.sources import SCRAPER_REGISTRY

logger = logging.getLogger(__name__)


# Canonical credential resolver (no embedded defaults) — see pipeline/config.py.
_get_db_connection = get_db_connection


def _ingest_fx(
    raw_records: list[dict[str, Any]],
    source_slug: str,
    scrape_date: str,
    engine: BronzeScraper,
    conn,
) -> dict[str, Any]:
    """Persists the MEF USD/KHR rate + raw snapshot (no product rows)."""
    rate: float | None = None
    is_fallback = False
    for rec in raw_records:
        if isinstance(rec, dict) and rec.get("rate") is not None:
            rate = float(rec["rate"])
            is_fallback = bool(rec.get("is_fallback", False))
            break
    if rate is None or rate <= 0:
        raise ValueError(f"Invalid MEF FX rate for {scrape_date}: {rate!r}")

    batch_id = uuid.uuid4()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO staging.raw_scrapes (
                run_id, store_slug, scrape_date, record_count, payload, source_type
            ) VALUES (%s, %s, %s::DATE, 1, %s::jsonb, 'fx')
            ON CONFLICT (scrape_date, store_slug) DO UPDATE
            SET run_id = EXCLUDED.run_id,
                record_count = EXCLUDED.record_count,
                payload = EXCLUDED.payload;
            """,
            (str(batch_id), source_slug, scrape_date, json.dumps(raw_records)),
        )
        engine.store_fx_rate(
            rate=rate,
            conn=conn,
            execution_date=scrape_date,
            source="fallback" if is_fallback else "official",
            raw_payload=raw_records,
            is_stale=is_fallback,
        )
    _record_fallback_stats(conn, source_slug, scrape_date, raw_records)
    return {"source_slug": source_slug, "records": 1, "fx_rate": rate, "is_fallback": is_fallback}


def _record_fallback_stats(
    conn, source_slug: str, scrape_date: str, records: list[dict[str, Any]]
) -> None:
    """Persists per-batch fallback counts to staging.fallback_alerts so
    baseline-only scrapes are observable and alertable (Risk 3).
    Guarded by a SAVEPOINT: database errors must never poison the transaction."""
    total = len(records)
    fallback = sum(1 for r in records if r.get("is_fallback"))
    try:
        with conn.cursor() as cur:
            cur.execute("SAVEPOINT fallback_stats_sp")
            try:
                cur.execute(
                    """
                    INSERT INTO staging.fallback_alerts
                        (scrape_date, store_slug, fallback_rows, total_rows)
                    VALUES (%s::DATE, %s, %s, %s)
                    ON CONFLICT (scrape_date, store_slug) DO UPDATE
                    SET fallback_rows = EXCLUDED.fallback_rows,
                        total_rows = EXCLUDED.total_rows,
                        created_at = NOW();
                    """,
                    (scrape_date, source_slug, fallback, total),
                )
                cur.execute("RELEASE SAVEPOINT fallback_stats_sp")
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT fallback_stats_sp")
                logger.warning(
                    "Could not record fallback stats for %s on %s: %s",
                    source_slug,
                    scrape_date,
                    exc,
                )
    except Exception as exc:
        logger.warning(
            "Could not manage savepoint for fallback stats for %s on %s: %s",
            source_slug,
            scrape_date,
            exc,
        )


def ingest_source_bronze(source_slug: str, scrape_date: str) -> dict[str, Any]:
    """
    Full Bronze ingestion for a single source:
        fetch â†’ normalize (Schema v1.0) â†’ zero-product gate â†’ DQ validate
        â†’ MinIO raw snapshot â†’ Parquet archive â†’ PostgreSQL staging/bronze
    """
    scraper_cls = SCRAPER_REGISTRY.get(source_slug)
    if not scraper_cls:
        raise ValueError(f"Unknown scraper source: {source_slug}")

    date_str = str(scrape_date)
    parsed_date = (
        datetime.fromisoformat(date_str).date() if isinstance(scrape_date, str) else scrape_date
    )
    raw_records = scraper_cls().fetch_records(scrape_date=parsed_date)
    if not raw_records:
        # Zero-Product Quality Gate (guide Â§1.5): raise before any DB write.
        raise ValueError(
            f"Zero-product quality gate: source '{source_slug}' returned 0 records on {date_str}"
        )

    engine = BronzeScraper()

    # FX path: short-circuit before normalization (no product records to normalize).
    # Acquire connection immediately since FX handling is not CPU-bound.
    if source_slug == "mef_fx":
        conn = _get_db_connection()
        try:
            result = _ingest_fx(raw_records, source_slug, date_str, engine, conn)
            conn.commit()
            return result
        finally:
            conn.close()

    # Normalize and validate BEFORE acquiring the DB connection so the
    # connection is not held open during CPU-bound text processing of large batches.
    records = normalize_records(
        raw_records,
        scrape_date=date_str,
        source_slug=source_slug,
    )
    dq = validate_records(records)
    if dq["error_count"] > 0:
        logger.warning(
            "DQ issues for %s on %s: %s",
            source_slug,
            date_str,
            dq["errors"][:5],
        )

    # Circuit Breaker Quality Gate: Evaluates volume drop and price velocity against rolling baseline
    try:
        from pipeline.circuit_breaker import IngestionCircuitBreaker, CircuitBreakerStatus
        cb = IngestionCircuitBreaker()
        eval_res = cb.evaluate_scrape(
            store_slug=source_slug,
            incoming_records=records,
            scrape_date=parsed_date,
        )
        if eval_res.status != CircuitBreakerStatus.PASSED:
            cb.record_event(eval_res, action_taken="warning_flagged")
            logger.warning(
                "Circuit breaker TRIPPED for %s on %s: %s — %s",
                source_slug,
                date_str,
                eval_res.status.value,
                eval_res.message,
            )
    except Exception as exc:
        logger.warning("Circuit breaker evaluation skipped for %s on %s: %s", source_slug, date_str, exc)

    conn = _get_db_connection()
    try:
        batch_id = uuid.uuid4()
        count = engine.write_canonical_batch(
            records=records,
            conn=conn,
            batch_id=batch_id,
            store_id=source_slug,
            source_name=source_slug,
            source_type=str(records[0].get("source_type", "web")),
            scrape_date=date_str,
        )
        _record_fallback_stats(conn, source_slug, date_str, records)
        conn.commit()
        return {
            "source_slug": source_slug,
            "records": len(records),
            "new_records": count,
            "batch_id": str(batch_id),
        }
    finally:
        conn.close()


def check_bronze_gate(source_slug: str, scrape_date: str) -> int:
    """
    Bronze DQ gate: verifies a non-empty staging.raw_scrapes row exists for the
    given source/date. Raises if the batch is missing or recorded 0 products.
    """
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT record_count FROM staging.raw_scrapes
                WHERE store_slug = %s AND scrape_date = %s::DATE
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (source_slug, scrape_date),
            )
            row = cur.fetchone()
        if not row:
            raise ValueError(
                f"Bronze gate failed: no staging.raw_scrapes row for {source_slug} on {scrape_date}"
            )
        count = row[0]
        if count <= 0:
            with conn.cursor() as cur_repair:
                cur_repair.execute(
                    "SELECT COUNT(*) FROM bronze.raw_prices WHERE source_name = %s AND scraped_at >= %s::date AND scraped_at < (%s::date + INTERVAL '1 day')",
                    (source_slug, scrape_date, scrape_date),
                )
                row_b = cur_repair.fetchone()
                if row_b and row_b[0] > 0:
                    count = row_b[0]
                    cur_repair.execute(
                        "UPDATE staging.raw_scrapes SET record_count = %s WHERE store_slug = %s AND scrape_date = %s::DATE",
                        (count, source_slug, scrape_date),
                    )
                    conn.commit()
                    logger.warning(
                        "Repaired staging.raw_scrapes record_count from bronze.raw_prices for %s on %s: %d records found",
                        source_slug, scrape_date, count
                    )
                    return count
            raise ValueError(
                f"Bronze gate failed: {source_slug} on {scrape_date} recorded 0 products"
            )
        return count
    finally:
        conn.close()
