"""
tests/test_circuit_breaker.py
─────────────────────────────
Unit tests for pipeline.circuit_breaker.
"""

from datetime import date
from unittest.mock import MagicMock
from pipeline.circuit_breaker import (
    IngestionCircuitBreaker,
    CircuitBreakerStatus,
    CircuitBreakerEvaluation,
)


def test_circuit_breaker_empty():
    """Verify that an empty record list immediately trips TRIPPED_EMPTY."""
    cb = IngestionCircuitBreaker()
    res = cb.evaluate_scrape(store_slug="test_store", incoming_records=[], scrape_date=date(2026, 9, 9))
    assert res.status == CircuitBreakerStatus.TRIPPED_EMPTY
    assert res.incoming_count == 0


def test_circuit_breaker_passed():
    """Verify that a normal scrape with stable volume and price passes."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Mock 7 days of historical scrapes: count=100, median_price=5000.0
    mock_cur.fetchall.return_value = [
        (date(2026, 9, 8), 100, 5000.0),
        (date(2026, 9, 7), 100, 5000.0),
        (date(2026, 9, 6), 102, 5050.0),
    ]

    cb = IngestionCircuitBreaker(conn=mock_conn)
    records = [{"price_khr": 5100.0} for _ in range(95)]
    res = cb.evaluate_scrape(store_slug="test_store", incoming_records=records, scrape_date=date(2026, 9, 9))

    assert res.status == CircuitBreakerStatus.PASSED
    assert res.incoming_count == 95
    assert res.volume_ratio >= 0.70


def test_circuit_breaker_volume_drop():
    """Verify that a >30% volume drop trips TRIPPED_VOLUME."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Historical count is 1000
    mock_cur.fetchall.return_value = [
        (date(2026, 9, 8), 1000, 10000.0),
        (date(2026, 9, 7), 1000, 10000.0),
    ]

    cb = IngestionCircuitBreaker(conn=mock_conn)
    # Only 500 records (50% of median, below 70% threshold)
    records = [{"price_khr": 10000.0} for _ in range(500)]
    res = cb.evaluate_scrape(store_slug="test_store", incoming_records=records, scrape_date=date(2026, 9, 9))

    assert res.status == CircuitBreakerStatus.TRIPPED_VOLUME
    assert res.volume_ratio == 0.50
    assert "VOLUME ANOMALY" in res.message


def test_circuit_breaker_price_velocity():
    """Verify that a >15% median price shift trips TRIPPED_PRICE_VELOCITY."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Historical median price is 10,000 KHR
    mock_cur.fetchall.return_value = [
        (date(2026, 9, 8), 100, 10000.0),
    ]

    cb = IngestionCircuitBreaker(conn=mock_conn)
    # Today median price is 13,000 KHR (+30% jump)
    records = [{"price_khr": 13000.0} for _ in range(100)]
    res = cb.evaluate_scrape(store_slug="test_store", incoming_records=records, scrape_date=date(2026, 9, 9))

    assert res.status == CircuitBreakerStatus.TRIPPED_PRICE_VELOCITY
    assert res.price_change_pct == 0.30
    assert "PRICE VELOCITY ANOMALY" in res.message


def test_circuit_breaker_record_event():
    """Verify that recording an event executes database insert."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    cb = IngestionCircuitBreaker(conn=mock_conn)
    eval_res = CircuitBreakerEvaluation(
        store_slug="test_store",
        scrape_date=date(2026, 9, 9),
        status=CircuitBreakerStatus.TRIPPED_VOLUME,
        incoming_count=50,
        rolling_median_count=100.0,
        incoming_median_price=5000.0,
        prior_median_price=5000.0,
        volume_ratio=0.50,
        price_change_pct=0.0,
        message="Volume dropped",
    )
    cb.record_event(eval_res, action_taken="quarantine")

    mock_cur.execute.assert_any_call("CREATE SCHEMA IF NOT EXISTS ops;")
    mock_conn.commit.assert_called()
