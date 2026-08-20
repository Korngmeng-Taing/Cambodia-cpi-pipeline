"""
tests/test_playwright_to_minio.py
─────────────────────────────────
Unit tests for the Playwright -> Parquet -> MinIO uploader (Prompt 1).
DB/network/browser-free: boto3 and Playwright are mocked.
"""

import uuid
from datetime import UTC, datetime

import pandas as pd
import pytest

from scrapers import playwright_to_minio as p2m


def _sample_records():
    return [
        {
            "raw_item_id": "P001",
            "raw_product_name": "Rice 5kg",
            "raw_price": "12500",
            "raw_currency": "KHR",
            "raw_unit_size": "5kg",
            "is_promotional": False,
            "source_url": "http://example.test",
        },
        {
            "raw_item_id": "P002",
            "raw_product_name": "Phone 8GB/256GB",
            "raw_price": "249.99",
            "raw_currency": "USD",
            "raw_unit_size": "",
            "is_promotional": "true",
            "source_url": "http://example.test",
        },
    ]


def test_build_bronze_frame_injects_metadata():
    batch_id = uuid.uuid4()
    ts = datetime(2026, 8, 18, 0, 0, tzinfo=UTC)
    df = p2m.build_bronze_frame(
        _sample_records(),
        source_name="supermarket_a",
        batch_id=batch_id,
        scrape_timestamp=ts,
    )
    assert len(df) == 2
    assert set(df.columns) >= {
        "scrape_batch_id",
        "scrape_timestamp",
        "scrape_date",
        "source_name",
        "raw_item_id",
        "raw_price",
        "raw_currency",
        "is_promotional",
    }
    assert df["scrape_batch_id"].iloc[0] == str(batch_id)
    assert df["scrape_date"].iloc[0] == "2026-08-18"
    assert df["source_name"].unique().tolist() == ["supermarket_a"]
    assert df["raw_price"].tolist() == [12500.0, 249.99]
    assert df["is_promotional"].dtype == bool


def test_build_bronze_frame_drops_non_numeric_prices():
    records = _sample_records() + [
        {
            "raw_item_id": "P003",
            "raw_product_name": "Broken price",
            "raw_price": "N/A",
            "raw_currency": "USD",
            "raw_unit_size": "",
            "is_promotional": False,
            "source_url": "http://example.test",
        }
    ]
    df = p2m.build_bronze_frame(records, source_name="supermarket_a")
    assert len(df) == 2
    assert "P003" not in df["raw_item_id"].values


def test_build_bronze_frame_rejects_empty():
    with pytest.raises(ValueError, match="0 products"):
        p2m.build_bronze_frame([], source_name="supermarket_a")


def test_write_snappy_parquet_roundtrip(tmp_path):
    df = p2m.build_bronze_frame(_sample_records(), source_name="supermarket_a")
    out = p2m.write_snappy_parquet(df, tmp_path)
    assert out.exists()
    assert out.suffix == ".parquet"
    back = pd.read_parquet(out, engine="pyarrow")
    assert len(back) == 2
    assert back["raw_price"].tolist() == [12500.0, 249.99]


class _FakeS3Client:
    def __init__(self):
        self.uploads = []
        self._exists = False

    def head_bucket(self, Bucket):
        if not self._exists:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, Bucket):
        self._exists = True

    def upload_file(self, local, bucket, key, ExtraArgs=None):
        self.uploads.append((local, bucket, key, ExtraArgs))


def test_upload_to_minio_uses_expected_key(monkeypatch, tmp_path):
    client = _FakeS3Client()
    monkeypatch.setattr(p2m, "get_s3_client", lambda: client)
    local = tmp_path / "x.parquet"
    local.write_bytes(b"parquet-bytes")

    batch_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    key = p2m.upload_to_minio(local, "supermarket_a", "2026-08-18", batch_id)

    assert (
        key
        == "source=supermarket_a/scrape_date=2026-08-18/12345678-1234-5678-1234-567812345678.parquet"
    )
    assert client.uploads[0][1] == p2m.MINIO_BUCKET
    assert client.uploads[0][2] == key


def test_upload_to_minio_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        p2m.upload_to_minio("does_not_exist.parquet", "s", "2026-08-18", uuid.uuid4())


def test_generic_scraper_extract_item_mock():
    class _FakeItem:
        def __init__(self, item_id):
            self.item_id = item_id

        def get_attribute(self, name):
            return self.item_id if name == "data-item-id" else None

        def inner_text(self):
            return "Rice 5kg"

    scraper = p2m.GenericPlaywrightScraper(source_name="s", start_url="http://x")
    rec = scraper._extract_item(_FakeItem("P1"))
    assert rec["raw_item_id"] == "P1"
    assert rec["raw_product_name"] == "Rice 5kg"
    assert rec["source_url"] == "http://x"
