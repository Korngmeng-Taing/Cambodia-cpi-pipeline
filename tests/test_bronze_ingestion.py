"""
tests/test_bronze_ingestion.py
──────────────────────────────
Unit tests for pipeline.bronze_ingestion (full Bronze ingestion + zero-product gate).
"""

from unittest.mock import MagicMock, patch

import pytest

from pipeline.bronze_ingestion import check_bronze_gate, ingest_source_bronze


@patch("pipeline.bronze_ingestion.BronzeScraper")
@patch("pipeline.bronze_ingestion._get_db_connection")
def test_ingest_source_bronze_product_path(mock_conn, mock_engine_cls):
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn.return_value = conn

    engine = mock_engine_cls.return_value
    engine.write_canonical_batch.return_value = 2

    canned_records = [
        {"source_slug": "delishop", "name": "Angkor Beer Can 330ml", "price": 0.85, "currency": "USD", "scrape_date": "2026-08-17"},
        {"source_slug": "delishop", "name": "Avocado Hass Fresh 500g", "price": 2.90, "currency": "USD", "scrape_date": "2026-08-17"},
    ]

    from scrapers.sources import DelishopScraper

    with patch.object(DelishopScraper, "fetch_records", return_value=canned_records):
        result = ingest_source_bronze("delishop", "2026-08-17")

    assert result["source_slug"] == "delishop"
    assert result["records"] == 2
    assert result["batch_id"]
    engine.write_canonical_batch.assert_called_once()
    conn.commit.assert_called_once()

    # canonical Schema v1.0 records must be what gets written
    records_arg = engine.write_canonical_batch.call_args.kwargs["records"]
    assert len(records_arg) == 2
    assert records_arg[0]["source_slug"] == "delishop"
    assert records_arg[0]["name"] == "Angkor Beer Can 330ml"
    assert records_arg[0]["price"] == 0.85
    assert "scrape_date" in records_arg[0]


@patch("pipeline.bronze_ingestion.BronzeScraper")
@patch("pipeline.bronze_ingestion._get_db_connection")
def test_ingest_source_bronze_zero_product_gate(mock_conn, mock_engine_cls):
    conn = MagicMock()
    mock_conn.return_value = conn

    # 'mef_fx' is not the zero-product source; use a registry source with records.
    # Patch fetch_records at the scraper level to return empty.
    from scrapers.sources import DelishopScraper

    with patch.object(DelishopScraper, "fetch_records", return_value=[]):
        with pytest.raises(ValueError, match="Zero-product quality gate"):
            ingest_source_bronze("delishop", "2026-08-17")

    # No DB writes must occur on the gate
    mock_engine_cls.assert_not_called()


@patch("pipeline.bronze_ingestion.BronzeScraper")
@patch("pipeline.bronze_ingestion._get_db_connection")
def test_ingest_source_bronze_unknown_source(mock_conn, mock_engine_cls):
    with pytest.raises(ValueError, match="Unknown scraper source"):
        ingest_source_bronze("not_a_source", "2026-08-17")


@patch("pipeline.bronze_ingestion.BronzeScraper")
@patch("pipeline.bronze_ingestion._get_db_connection")
def test_ingest_fx_path(mock_conn, mock_engine_cls):
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn.return_value = conn

    engine = mock_engine_cls.return_value

    from scrapers.sources import MefExchangeRateScraper

    canned_fx = [{"rate": 4050.0, "scrape_date": "2026-08-17", "source_slug": "mef_fx", "source_type": "fx"}]
    with patch.object(MefExchangeRateScraper, "fetch_records", return_value=canned_fx):
        result = ingest_source_bronze("mef_fx", "2026-08-17")

    assert result["source_slug"] == "mef_fx"
    assert result["fx_rate"] == 4050.0
    engine.store_fx_rate.assert_called_once()
    engine.write_canonical_batch.assert_not_called()
    engine.minio.put_json.assert_called_once()


@patch("pipeline.bronze_ingestion._get_db_connection")
def test_check_bronze_gate_success(mock_conn):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (7,)
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn.return_value = conn

    assert check_bronze_gate("aeon", "2026-08-17") == 7


@patch("pipeline.bronze_ingestion._get_db_connection")
def test_check_bronze_gate_missing_row(mock_conn):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn.return_value = conn

    with pytest.raises(ValueError, match="no staging.raw_scrapes row"):
        check_bronze_gate("aeon", "2026-08-17")
