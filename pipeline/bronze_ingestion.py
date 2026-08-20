"""
pipeline/bronze_ingestion.py
────────────────────────────
Bronze ingestion entrypoint used by the per-source Airflow scraper DAGs.

Flow (adheres to SCRAPER_METHODOLOGY_GUIDE.md §1 & §3):
    fetch_records ─► canonical.normalize_records (Schema v1.0)
      ─► zero-product quality gate ─► DQ validate
      ─► MinIO raw snapshot (s3://cpi-bronze/{store}/dt={date}/raw.json)
      ─► Parquet cold archive ─► PostgreSQL staging.raw_scrapes + bronze.raw_prices

The MEF USD/KHR exchange rate is routed separately to staging.exchange_rates.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import pendulum
import psycopg2

from pipeline.bronze_scraper import BronzeScraper
from pipeline.canonical import normalize_records, validate_records
from scrapers.sources import SCRAPER_REGISTRY

logger = logging.getLogger(__name__)

DEFAULT_USD_KHR_RATE = float(os.getenv("DEFAULT_USD_KHR_RATE", "4044"))


def _get_db_connection():
    conn_str = os.getenv(
        "CPI_DATABASE_URL",
        "postgresql://cpi_user:cpi_pass@postgres:5432/cpi_db",
    )
    conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
    try:
        return psycopg2.connect(conn_str)
    except psycopg2.OperationalError:
        if "postgres" in conn_str:
            alt = conn_str.replace("postgres:5432", "localhost:5432")
        else:
            alt = conn_str.replace("localhost:5432", "postgres:5432")
        return psycopg2.connect(alt)


def _ingest_fx(
    raw_records: list[dict[str, Any]],
    source_slug: str,
    scrape_date: str,
    engine: BronzeScraper,
    conn,
) -> dict[str, Any]:
    """Persists the MEF USD/KHR rate + raw snapshot (no product rows)."""
    rate: float | None = None
    for rec in raw_records:
        if isinstance(rec, dict) and rec.get("rate") is not None:
            rate = float(rec["rate"])
            break
    if rate is None or rate <= 0:
        raise ValueError(f"Invalid MEF FX rate for {scrape_date}: {rate!r}")

    batch_id = uuid.uuid4()

    # Raw snapshot to MinIO (fail loud: no local fallback)
    engine.minio.put_json(source_slug, raw_records, scrape_date=scrape_date)

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
            source="official",
            raw_payload=raw_records,
            is_stale=False,
        )
    return {"source_slug": source_slug, "records": 1, "fx_rate": rate}


def ingest_source_bronze(source_slug: str, scrape_date: str) -> dict[str, Any]:
    """
    Full Bronze ingestion for a single source:
        fetch → normalize (Schema v1.0) → zero-product gate → DQ validate
        → MinIO raw snapshot → Parquet archive → PostgreSQL staging/bronze
    """
    scraper_cls = SCRAPER_REGISTRY.get(source_slug)
    if not scraper_cls:
        raise ValueError(f"Unknown scraper source: {source_slug}")

    date_str = str(scrape_date)
    parsed_date = (
        pendulum.parse(date_str).date() if isinstance(scrape_date, str) else scrape_date
    )
    raw_records = scraper_cls().fetch_records(scrape_date=parsed_date)
    if not raw_records:
        # Zero-Product Quality Gate (guide §1.5): raise before any DB write.
        raise ValueError(
            f"Zero-product quality gate: source '{source_slug}' returned 0 records on {date_str}"
        )

    conn = _get_db_connection()
    engine = BronzeScraper()
    try:
        if source_slug == "mef_fx":
            result = _ingest_fx(raw_records, source_slug, date_str, engine, conn)
            conn.commit()
            return result

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
        conn.commit()
        return {"source_slug": source_slug, "records": count, "batch_id": str(batch_id)}
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
            raise ValueError(
                f"Bronze gate failed: {source_slug} on {scrape_date} recorded 0 products"
            )
        return count
    finally:
        conn.close()
