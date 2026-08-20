"""
pipeline/bronze_scraper.py
──────────────────────────
Bronze Layer Scraper & Ingestion Engine.

Responsibilities:
- Fetches raw listings from e-commerce sources.
- Saves raw JSON payload to MinIO (S3-compatible cold object storage).
- Appends immutable, unmodified records to `bronze.raw_prices` & `staging.raw_scrapes` in PostgreSQL.
- Archives partitioned Parquet files (`ParquetArchiver`).
- Resilient retries and non-blocking error logging to `bronze.scrape_errors`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import requests
from psycopg2.extensions import connection

from pipeline.minio_storage import MinioStorage
from pipeline.parquet_archiver import ParquetArchiver

logger = logging.getLogger(__name__)


class BronzeScraper:
    def __init__(self):
        self.minio = MinioStorage()
        self.archiver = ParquetArchiver()

    def parse_records(self, raw_data: Any, source_name: str, store_id: str) -> list[dict[str, Any]]:
        """Parses raw HTML/JSON into record dicts."""
        records = []
        parsed_data = raw_data
        if isinstance(raw_data, str):
            try:
                parsed_data = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON string. Falling back to empty.")
                return records

        if not isinstance(parsed_data, list):
            parsed_data = [parsed_data]

        for item in parsed_data:
            if not isinstance(item, dict):
                continue

            desc = item.get("item_description") or item.get("name") or item.get("item_description_raw")
            price = item.get("price")
            if desc and price is not None:
                try:
                    p_val = float(price)
                    records.append({
                        "item_description_raw": str(desc),
                        "price": p_val,
                        "currency": item.get("currency", "USD"),
                        "source_url": item.get("url") or item.get("source_url", ""),
                        "raw_payload": json.dumps(item),
                    })
                except (ValueError, TypeError):
                    continue
        return records

    def _existing_keys(
        self,
        conn: connection,
        store_id: str,
        source_name: str,
        scrape_date: str | None,
    ) -> set[tuple[str, str, float]]:
        """Returns (source_url, item_description_raw, price) tuples already ingested
        for this store on the target date, so re-scrapes do not duplicate rows."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(source_url, ''), item_description_raw, price
                FROM bronze.raw_prices
                WHERE store_id = %s AND source_name = %s
                  AND scraped_at::date = %s::date
                """,
                (store_id, source_name, scrape_date or time.strftime("%Y-%m-%d")),
            )
            return {(row[0], row[1], float(row[2])) for row in cur.fetchall()}

    def write_batch(
        self,
        records: list[dict[str, Any]],
        conn: connection,
        batch_id: uuid.UUID,
        store_id: str,
        source_name: str,
        scrape_date: str | None = None,
    ) -> int:
        """Writes parsed records to bronze.raw_prices and staging.raw_scrapes in a transaction."""
        if not records:
            return 0

        # Deduplicate against already-ingested rows for this store/date.
        existing = self._existing_keys(conn, store_id, source_name, scrape_date)
        records = [
            r for r in records
            if (r.get("source_url", "") or "", r.get("item_description_raw", ""), float(r.get("price") or 0))
            not in existing
        ]
        if not records:
            return 0

        # 1. Write to MinIO S3 Object Storage (fail loud: no local fallback)
        self.minio.put_json(store_id, records, scrape_date=scrape_date)

        # 2. Write to Parquet cold archive (MinIO only)
        self.archiver.archive_records(store_id, records, scrape_date=scrape_date)

        # 3. Write to PostgreSQL bronze.raw_prices
        insert_query = """
            INSERT INTO bronze.raw_prices (
                store_id, item_description_raw, price, currency,
                source_url, source_name, batch_id, raw_payload
            ) VALUES (
                %(store_id)s, %(item_description_raw)s, %(price)s, %(currency)s,
                %(source_url)s, %(source_name)s, %(batch_id)s, %(raw_payload)s::jsonb
            )
        """
        count = 0
        with conn.cursor() as cur:
            for record in records:
                record_data = {
                    "store_id": store_id,
                    "source_name": source_name,
                    "batch_id": str(batch_id),
                    **record,
                }
                cur.execute(insert_query, record_data)
                count += 1

            # 4. Upsert staging.raw_scrapes batch record
            cur.execute(
                """
                INSERT INTO staging.raw_scrapes (
                    run_id, store_slug, scrape_date, record_count, payload, source_type
                ) VALUES (%s, %s, %s::DATE, %s, %s::jsonb, 'web')
                ON CONFLICT (scrape_date, store_slug) DO UPDATE
                SET run_id = EXCLUDED.run_id,
                    record_count = EXCLUDED.record_count,
                    payload = EXCLUDED.payload;
                """,
                (
                    str(batch_id),
                    store_id,
                    scrape_date or time.strftime("%Y-%m-%d"),
                    count,
                    json.dumps(records),
                ),
            )
        return count

    def write_canonical_batch(
        self,
        records: list[dict[str, Any]],
        conn: connection,
        batch_id: uuid.UUID,
        store_id: str,
        source_name: str,
        source_type: str = "web",
        scrape_date: str | None = None,
    ) -> int:
        """
        Writes FULL canonical Bronze Schema v1.0 records end-to-end:

        1. Raw JSON snapshot to MinIO: s3://cpi-bronze/{store}/dt={date}/raw.json
        2. Parquet cold archive (full canonical payload)
        3. bronze.raw_prices append (full canonical payload preserved as raw_payload)
        4. staging.raw_scrapes upsert (append-only, one row per day/store)
        """
        if not records:
            return 0

        # 1. Full raw payload to MinIO (guide layout; fail loud)
        self.minio.put_json(store_id, records, scrape_date=scrape_date)

        # 2. Parquet cold archive (MinIO only)
        self.archiver.archive_records(store_id, records, scrape_date=scrape_date)

        # 3. Parse canonical records into bronze.raw_prices rows
        parsed = self.parse_records(records, source_name, store_id)
        existing = self._existing_keys(conn, store_id, source_name, scrape_date)
        parsed = [
            r for r in parsed
            if (r.get("source_url", "") or "", r.get("item_description_raw", ""), float(r.get("price") or 0))
            not in existing
        ]
        insert_query = """
            INSERT INTO bronze.raw_prices (
                store_id, item_description_raw, price, currency,
                source_url, source_name, batch_id, raw_payload
            ) VALUES (
                %(store_id)s, %(item_description_raw)s, %(price)s, %(currency)s,
                %(source_url)s, %(source_name)s, %(batch_id)s, %(raw_payload)s::jsonb
            )
        """
        count = 0
        with conn.cursor() as cur:
            for record in parsed:
                record_data = {
                    "store_id": store_id,
                    "source_name": source_name,
                    "batch_id": str(batch_id),
                    **record,
                }
                cur.execute(insert_query, record_data)
                count += 1

            # 4. Upsert staging.raw_scrapes batch record
            cur.execute(
                """
                INSERT INTO staging.raw_scrapes (
                    run_id, store_slug, scrape_date, record_count, payload, source_type
                ) VALUES (%s, %s, %s::DATE, %s, %s::jsonb, %s)
                ON CONFLICT (scrape_date, store_slug) DO UPDATE
                SET run_id = EXCLUDED.run_id,
                    record_count = EXCLUDED.record_count,
                    payload = EXCLUDED.payload;
                """,
                (
                    str(batch_id),
                    store_id,
                    scrape_date or time.strftime("%Y-%m-%d"),
                    len(records),
                    json.dumps(records),
                    source_type,
                ),
            )
        return len(records)

    def store_fx_rate(
        self,
        rate: float,
        conn: connection,
        execution_date: str,
        source: str = "official",
        raw_payload: Any | None = None,
        is_stale: bool = False,
    ) -> None:
        """
        Upserts the daily USD/KHR exchange rate into staging.exchange_rates.
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO staging.exchange_rates (
                    execution_date, rate, source, is_stale, raw_payload, fetched_at
                ) VALUES (%s::DATE, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (execution_date) DO UPDATE
                SET rate = EXCLUDED.rate,
                    source = EXCLUDED.source,
                    is_stale = EXCLUDED.is_stale,
                    raw_payload = EXCLUDED.raw_payload,
                    fetched_at = NOW();
                """,
                (execution_date, rate, source, is_stale, json.dumps(raw_payload) if raw_payload is not None else None),
            )

    def log_error(
        self,
        batch_id: uuid.UUID,
        store_id: str,
        source_name: str,
        raw_record: str,
        error_type: str,
        error_message: str,
        conn: connection,
    ):
        """Logs malformed records to bronze.scrape_errors."""
        insert_query = """
            INSERT INTO bronze.scrape_errors (
                batch_id, store_id, source_name, raw_record, error_type, error_message
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
        """
        try:
            with conn.cursor() as cur:
                cur.execute(
                    insert_query,
                    (
                        str(batch_id) if batch_id else None,
                        store_id,
                        source_name,
                        raw_record,
                        error_type,
                        error_message,
                    ),
                )
        except Exception as e:
            logger.error("Failed to log error: %s", e)

    def scrape_and_ingest(
        self,
        store_id: str,
        source_name: str,
        source_url: str,
        conn: connection,
    ) -> None:
        """Orchestrates fetch, parse, and write with retry (3 attempts) and error logging."""
        batch_id = uuid.uuid4()
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # 1. Fetch (retryable on network failure)
                response = requests.get(source_url, timeout=10)
                response.raise_for_status()
                raw_data = response.text
            except Exception as exc:
                if attempt == max_retries - 1:
                    self.log_error(batch_id, store_id, source_name, "", "ScrapeNetworkError", str(exc), conn)
                    conn.commit()
                    return
                time.sleep(0.1)
                continue

            try:
                # 2. Parse
                records = self.parse_records(raw_data, source_name, store_id)

                # 2.5 Log malformed records explicitly
                try:
                    parsed_json = json.loads(raw_data)
                    if not isinstance(parsed_json, list):
                        parsed_json = [parsed_json]
                    for item in parsed_json:
                        if isinstance(item, dict) and ("item_description" not in item or "price" not in item):
                            self.log_error(
                                batch_id,
                                store_id,
                                source_name,
                                json.dumps(item),
                                "ValidationError",
                                "Missing item_description or price",
                                conn,
                            )
                except Exception:
                    pass

                # 3. Write
                self.write_batch(records, conn, batch_id, store_id, source_name)
                conn.commit()
                return

            except Exception as e:
                conn.rollback()
                self.log_error(batch_id, store_id, source_name, "", "ScrapeIngestionError", str(e), conn)
                conn.commit()
                return
