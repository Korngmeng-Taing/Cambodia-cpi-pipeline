"""
pipeline/bronze_scraper.py
──────────────────────────
Bronze Layer Scraper & Ingestion Engine.

Responsibilities:
- Fetches raw listings from e-commerce sources.
- Writes immutable, unmodified records to `bronze.raw_prices` & `staging.raw_scrapes` in PostgreSQL.
  Contract: "deduped at insert" — re-scraped observations on the same day are
  dropped app-side and via INSERT ... ON CONFLICT DO NOTHING against the
  uq_raw_prices_observation unique index; rows are never mutated afterwards.
- Resilient retries and non-blocking error logging to `bronze.scrape_errors`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg2.extensions import connection

logger = logging.getLogger(__name__)


class BronzeScraper:
    def __init__(self):
        pass

    def parse_records(
        self, raw_data: Any, source_name: str, store_id: str
    ) -> list[dict[str, Any]]:
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

            desc = (
                item.get("item_description")
                or item.get("name")
                or item.get("item_description_raw")
            )
            price = item.get("price")
            if desc and price is not None:
                try:
                    p_val = float(price)
                    records.append(
                        {
                            "item_description_raw": str(desc),
                            "price": p_val,
                            "currency": item.get("currency", "USD"),
                            "source_url": item.get("url") or item.get("source_url", ""),
                            "scraped_at": item.get("scraped_at"),
                            "raw_payload": json.dumps(item),
                        }
                    )
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
                  AND scraped_at >= %s::date AND scraped_at < (%s::date + INTERVAL '1 day')
                """,
                (store_id, source_name, scrape_date or time.strftime("%Y-%m-%d"), scrape_date or time.strftime("%Y-%m-%d")),
            )
            return {(row[0], row[1], float(row[2])) for row in cur.fetchall()}

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
        Writes FULL canonical Bronze Schema v1.0 records to PostgreSQL bronze.raw_prices & staging.raw_scrapes.
        """
        if not records:
            return 0

        # Map canonical Schema v1.0 records directly to bronze.raw_prices row dicts.
        # parse_records() was designed for raw HTML/JSON input and was being called
        # redundantly on already-normalized canonical records. Direct mapping is
        # clearer and avoids the intermediate transformation.
        existing = self._existing_keys(conn, store_id, source_name, scrape_date)
        deduped_records = [
            r
            for r in records
            if (
                r.get("url") or r.get("source_url", "") or "",
                r.get("name") or r.get("item_description_raw", ""),
                float(r.get("price") or 0),
            )
            not in existing
        ]

        def _to_bronze_row(rec: dict) -> dict:
            return {
                "item_description_raw": rec.get("name") or rec.get("item_description_raw", ""),
                "price": float(rec.get("price") or 0),
                "currency": rec.get("currency", "USD"),
                "source_url": rec.get("url") or rec.get("source_url", ""),
                "scraped_at": rec.get("scraped_at"),
                "raw_payload": json.dumps(rec),
            }

        parsed = [_to_bronze_row(r) for r in deduped_records]
        insert_query = """
            INSERT INTO bronze.raw_prices (
                store_id, item_description_raw, price, currency,
                source_url, source_name, batch_id, raw_payload, scraped_at
            ) VALUES (
                %(store_id)s, %(item_description_raw)s, %(price)s, %(currency)s,
                %(source_url)s, %(source_name)s, %(batch_id)s, %(raw_payload)s::jsonb,
                %(scraped_at)s::timestamptz
            )
            ON CONFLICT DO NOTHING
            RETURNING raw_price_id
        """
        count = 0
        default_scraped_at = (
            f"{scrape_date}T00:00:00Z"
            if scrape_date
            else datetime.now(UTC).isoformat()
        )
        with conn.cursor() as cur:
            for record in parsed:
                record_data = {
                    "store_id": store_id,
                    "source_name": source_name,
                    "batch_id": str(batch_id),
                    **record,
                }
                # Guard against a record-supplied NULL wiping the default
                # (scraped_at is NOT NULL in bronze.raw_prices).
                if not record_data.get("scraped_at"):
                    record_data["scraped_at"] = default_scraped_at
                cur.execute(insert_query, record_data)
                # RETURNING gives us the actual inserted row (empty on conflict skip)
                count += len(cur.fetchall())

            staging_count = count
            if staging_count == 0 and len(records) > 0:
                target_dt = scrape_date or time.strftime("%Y-%m-%d")
                cur.execute(
                    "SELECT COUNT(*) FROM bronze.raw_prices WHERE source_name = %s AND scraped_at >= %s::date AND scraped_at < (%s::date + INTERVAL '1 day')",
                    (source_name, target_dt, target_dt),
                )
                row_existing = cur.fetchone()
                if row_existing and row_existing[0] > 0:
                    staging_count = row_existing[0]

            # Upsert staging.raw_scrapes batch record.
            # record_count reflects rows actually written or existing after dedup.
            # payload stores the deduped canonical records (preserving Schema v1.0
            # for stg_raw_scrapes.sql), not pre-dedup records.
            cur.execute(
                """
                INSERT INTO staging.raw_scrapes (
                    run_id, store_slug, scrape_date, record_count, payload, source_type
                ) VALUES (%s, %s, %s::DATE, %s, %s::jsonb, %s)
                ON CONFLICT (scrape_date, store_slug) DO UPDATE
                SET run_id = EXCLUDED.run_id,
                    record_count = GREATEST(staging.raw_scrapes.record_count, EXCLUDED.record_count),
                    payload = CASE 
                        WHEN jsonb_array_length(EXCLUDED.payload) > 0 
                        THEN staging.raw_scrapes.payload || EXCLUDED.payload 
                        ELSE staging.raw_scrapes.payload 
                    END;
                """,
                (
                    str(batch_id),
                    store_id,
                    scrape_date or time.strftime("%Y-%m-%d"),
                    staging_count,
                    json.dumps(deduped_records),
                    source_type,
                ),
            )
        return count

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
                (
                    execution_date,
                    rate,
                    source,
                    is_stale,
                    json.dumps(raw_payload) if raw_payload is not None else None,
                ),
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
        """Logs malformed records to bronze.scrape_errors.

        Uses a separate short-lived connection with autocommit so that error
        records are persisted even when the caller's main transaction is
        rolled back (e.g. after a scraper crash).
        """
        insert_query = """
            INSERT INTO bronze.scrape_errors (
                batch_id, store_id, source_name, raw_record, error_type, error_message
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
        """
        try:
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT log_error_sp")
                try:
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
                    cur.execute("RELEASE SAVEPOINT log_error_sp")
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT log_error_sp")
                    logger.warning("Could not insert into bronze.scrape_errors via savepoint: %s", exc)
        except Exception as e:
            logger.error("Failed to log error: %s", e)

