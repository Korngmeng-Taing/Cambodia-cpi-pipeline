"""
tests/test_nis_cpi_importer.py
───────────────────────────────
Unit tests for pipeline.nis_cpi_importer and scrapers.sources.nis_cpi.
"""

import os
import tempfile
from unittest.mock import MagicMock

from pipeline.nis_cpi_importer import NISBenchmarkImporter
from scrapers.sources.nis_cpi import NISCPIScraper


def test_nis_importer_sync_seed_csv():
    """Verify that sync_to_seed_csv properly formats, updates, and sorts rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_seed = os.path.join(tmpdir, "test_nis.csv")

        # Initial content with one row
        with open(test_seed, "w", encoding="utf-8") as f:
            f.write("cpi_month,headline_cpi,core_cpi,mom_inflation_pct,yoy_inflation_pct,release_date,source_notes\n")
            f.write("2026-07-01,100.3500,100.4000,0.1497,1.8000,2026-08-20,Test\n")

        importer = NISBenchmarkImporter(seed_file_path=test_seed)

        # Ingest a new month (2026-08-01)
        res = importer.ingest_record(
            cpi_month="2026-08-01",
            headline_cpi=100.55,
            core_cpi=100.60,
            mom_inflation_pct=0.1993,
            yoy_inflation_pct=1.8500,
            release_date="2026-09-20",
            source_notes="NIS Cambodia Official Release August 2026",
            sync_seed=True,
            conn=None,  # skip DB in unit test
        )

        assert res["status"] in ("success", "partial")
        assert res["seed_status"] == "synced"

        # Verify file contents
        with open(test_seed, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3  # Header + 2 rows
        assert "2026-08-01" in lines[2]
        assert "100.5500" in lines[2]


def test_nis_importer_db_upsert():
    """Verify that database upsert SQL is executed with correct parameters."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with tempfile.TemporaryDirectory() as tmpdir:
        test_seed = os.path.join(tmpdir, "test_nis.csv")
        importer = NISBenchmarkImporter(seed_file_path=test_seed)

        res = importer.ingest_record(
            cpi_month="2026-08-01",
            headline_cpi=100.55,
            core_cpi=100.60,
            mom_inflation_pct=0.1993,
            yoy_inflation_pct=1.8500,
            release_date="2026-09-20",
            source_notes="NIS Cambodia Official Release August 2026",
            sync_seed=True,
            conn=mock_conn,
        )

        assert res["status"] == "success"
        assert res["db_status"] == "upserted"
        mock_cur.execute.assert_any_call("CREATE SCHEMA IF NOT EXISTS gold;")
        mock_conn.commit.assert_called_once()


def test_nis_cpi_scraper_interface():
    """Verify NISCPIScraper returns valid Bronze record format."""
    scraper = NISCPIScraper()
    records = scraper.fetch_records()
    assert isinstance(records, list)
    if records:
        assert "name" in records[0]
        assert "price" in records[0]
        assert "currency" in records[0]
