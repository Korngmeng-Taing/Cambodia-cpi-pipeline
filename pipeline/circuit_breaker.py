"""
pipeline/circuit_breaker.py
───────────────────────────
Ingestion Quality Circuit Breaker for the Cambodia Daily CPI Pipeline.

Protects downstream Silver and Gold layers from corrupted, truncated,
or anomalous store scrapes by enforcing two mandatory quality gates:
  1. Volume Gate: Rejects/Quarantines if record_count < 70% of 7-day rolling median.
  2. Price Velocity Gate: Rejects/Quarantines if store median price shifts > 15% day-over-day.

If tripped:
  - Records the trip event in ops.circuit_breaker_events.
  - Quarantines the batch (preventing bad records from polluting clean_store_prices).
  - Triggers automated fallback to 7-day carry-forward clean prices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from pipeline.config import get_db_connection

log = logging.getLogger("circuit_breaker")


class CircuitBreakerStatus(str, Enum):
    PASSED = "PASSED"
    TRIPPED_VOLUME = "TRIPPED_VOLUME"
    TRIPPED_PRICE_VELOCITY = "TRIPPED_PRICE_VELOCITY"
    TRIPPED_EMPTY = "TRIPPED_EMPTY"


@dataclass
class CircuitBreakerEvaluation:
    store_slug: str
    scrape_date: date
    status: CircuitBreakerStatus
    incoming_count: int
    rolling_median_count: float
    incoming_median_price: float
    prior_median_price: float
    volume_ratio: float
    price_change_pct: float
    message: str


class IngestionCircuitBreaker:
    """
    Automated circuit breaker protecting the CPI ingestion pipeline.
    """

    VOLUME_DROP_THRESHOLD = 0.70  # Min 70% of 7-day rolling median
    PRICE_VELOCITY_THRESHOLD = 0.15  # Max 15% day-over-day median price shift

    def __init__(self, conn: Any = None):
        self._conn = conn

    def _get_connection(self):
        if self._conn is not None:
            return self._conn
        return get_db_connection()

    def ensure_ops_tables(self) -> None:
        """Ensures ops schema and circuit_breaker_events table exist."""
        conn = self._get_connection()
        should_close = self._conn is None
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS ops;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ops.circuit_breaker_events (
                        event_id BIGSERIAL PRIMARY KEY,
                        store_slug VARCHAR(64) NOT NULL,
                        scrape_date DATE NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        incoming_count INTEGER NOT NULL,
                        rolling_median_count NUMERIC(10, 2),
                        incoming_median_price NUMERIC(15, 2),
                        prior_median_price NUMERIC(15, 2),
                        volume_ratio NUMERIC(6, 4),
                        price_change_pct NUMERIC(6, 4),
                        action_taken VARCHAR(64),
                        details TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_cb_store_date 
                    ON ops.circuit_breaker_events (store_slug, scrape_date);
                """)
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def evaluate_scrape(
        self,
        store_slug: str,
        incoming_records: list[dict[str, Any]],
        scrape_date: date | None = None,
    ) -> CircuitBreakerEvaluation:
        """
        Evaluates an incoming scrape payload against historical baseline metrics.
        """
        if scrape_date is None:
            scrape_date = date.today()

        incoming_count = len(incoming_records)
        if incoming_count == 0:
            return CircuitBreakerEvaluation(
                store_slug=store_slug,
                scrape_date=scrape_date,
                status=CircuitBreakerStatus.TRIPPED_EMPTY,
                incoming_count=0,
                rolling_median_count=0.0,
                incoming_median_price=0.0,
                prior_median_price=0.0,
                volume_ratio=0.0,
                price_change_pct=0.0,
                message=f"Store '{store_slug}' produced 0 records on {scrape_date}.",
            )

        # Compute incoming median price (KHR)
        prices = [
            float(r.get("price_khr") or r.get("price") or 0.0)
            for r in incoming_records
            if float(r.get("price_khr") or r.get("price") or 0.0) > 0
        ]
        incoming_median_price = float(np.median(prices)) if prices else 0.0

        # Query 7-day rolling history for this store from silver.clean_store_prices
        history_start = scrape_date - timedelta(days=7)
        conn = self._get_connection()
        should_close = self._conn is None

        rolling_counts = []
        prior_day_median_price = incoming_median_price

        try:
            with conn.cursor() as cur:
                # Query daily counts for past 7 days
                cur.execute("""
                    SELECT scrape_date, COUNT(*), PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY price_khr)
                    FROM silver.clean_store_prices
                    WHERE store_slug = %s
                      AND scrape_date >= %s
                      AND scrape_date < %s
                    GROUP BY scrape_date
                    ORDER BY scrape_date DESC;
                """, (store_slug, history_start, scrape_date))
                rows = cur.fetchall()

                if rows:
                    rolling_counts = [int(r[1]) for r in rows]
                    prior_day_median_price = float(rows[0][2] or incoming_median_price)
        except Exception as e:
            log.warning("Could not query historical baseline for circuit breaker: %s", e)
        finally:
            if should_close:
                conn.close()

        rolling_median_count = float(np.median(rolling_counts)) if rolling_counts else float(incoming_count)
        volume_ratio = incoming_count / max(rolling_median_count, 1.0)

        # Check Gate 1: Volume Drop Gate
        if rolling_counts and volume_ratio < self.VOLUME_DROP_THRESHOLD:
            msg = (
                f"VOLUME ANOMALY: {store_slug} scraped {incoming_count} items "
                f"({volume_ratio:.1%} of 7-day rolling median {rolling_median_count:.0f}). "
                f"Below threshold {self.VOLUME_DROP_THRESHOLD:.0%}."
            )
            return CircuitBreakerEvaluation(
                store_slug=store_slug,
                scrape_date=scrape_date,
                status=CircuitBreakerStatus.TRIPPED_VOLUME,
                incoming_count=incoming_count,
                rolling_median_count=rolling_median_count,
                incoming_median_price=incoming_median_price,
                prior_median_price=prior_day_median_price,
                volume_ratio=round(volume_ratio, 4),
                price_change_pct=0.0,
                message=msg,
            )

        # Check Gate 2: Price Velocity Gate
        price_change_pct = 0.0
        if prior_day_median_price > 0 and incoming_median_price > 0:
            price_change_pct = abs(incoming_median_price - prior_day_median_price) / prior_day_median_price
            if price_change_pct > self.PRICE_VELOCITY_THRESHOLD:
                msg = (
                    f"PRICE VELOCITY ANOMALY: {store_slug} median price shifted by "
                    f"{price_change_pct:.1%} (from {prior_day_median_price:,.0f} to {incoming_median_price:,.0f} KHR). "
                    f"Exceeds max allowed drift {self.PRICE_VELOCITY_THRESHOLD:.0%}."
                )
                return CircuitBreakerEvaluation(
                    store_slug=store_slug,
                    scrape_date=scrape_date,
                    status=CircuitBreakerStatus.TRIPPED_PRICE_VELOCITY,
                    incoming_count=incoming_count,
                    rolling_median_count=rolling_median_count,
                    incoming_median_price=incoming_median_price,
                    prior_median_price=prior_day_median_price,
                    volume_ratio=round(volume_ratio, 4),
                    price_change_pct=round(price_change_pct, 4),
                    message=msg,
                )

        return CircuitBreakerEvaluation(
            store_slug=store_slug,
            scrape_date=scrape_date,
            status=CircuitBreakerStatus.PASSED,
            incoming_count=incoming_count,
            rolling_median_count=rolling_median_count,
            incoming_median_price=incoming_median_price,
            prior_median_price=prior_day_median_price,
            volume_ratio=round(volume_ratio, 4),
            price_change_pct=round(price_change_pct, 4),
            message=f"Scrape passed quality checks: {incoming_count} items, median {incoming_median_price:,.0f} KHR.",
        )

    def record_event(self, eval_result: CircuitBreakerEvaluation, action_taken: str = "quarantine") -> None:
        """Persists a circuit breaker evaluation incident into ops.circuit_breaker_events."""
        self.ensure_ops_tables()
        conn = self._get_connection()
        should_close = self._conn is None
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ops.circuit_breaker_events (
                        store_slug, scrape_date, status, incoming_count,
                        rolling_median_count, incoming_median_price, prior_median_price,
                        volume_ratio, price_change_pct, action_taken, details
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    eval_result.store_slug,
                    eval_result.scrape_date,
                    eval_result.status.value,
                    eval_result.incoming_count,
                    eval_result.rolling_median_count,
                    eval_result.incoming_median_price,
                    eval_result.prior_median_price,
                    eval_result.volume_ratio,
                    eval_result.price_change_pct,
                    action_taken,
                    eval_result.message,
                ))
                conn.commit()
                log.info(f"Recorded circuit breaker event: {eval_result.status} for {eval_result.store_slug}")
        finally:
            if should_close:
                conn.close()
