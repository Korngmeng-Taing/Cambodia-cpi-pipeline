"""
tests/test_parquet_archiver.py
──────────────────────────────
Unit tests for ParquetArchiver (streams to MinIO only, no local filesystem).
"""

import io

import pandas as pd

from pipeline.parquet_archiver import ParquetArchiver


class _FakeMinio:
    """Stand-in for MinioStorage capturing byte payloads in memory."""

    def __init__(self):
        self.objects = {}
        self.bucket_name = "cpi-bronze"

    def put_bytes(self, s3_key, body, content_type="application/octet-stream"):
        self.objects[s3_key] = body
        return f"s3://{self.bucket_name}/{s3_key}"

    def get_bytes(self, s3_key):
        if s3_key not in self.objects:
            raise RuntimeError(f"not found: {s3_key}")
        return self.objects[s3_key]


def test_parquet_archive_streams_to_minio(monkeypatch):
    fake = _FakeMinio()
    monkeypatch.setattr("pipeline.parquet_archiver.MinioStorage", lambda: fake)

    archiver = ParquetArchiver()
    sample_records = [
        {"item_description_raw": "Jasmine Rice 5kg", "price": 4.50, "currency": "USD"},
        {
            "item_description_raw": "Coca Cola 330ml Can",
            "price": 0.65,
            "currency": "USD",
        },
    ]

    s3_key = archiver.archive_records(
        "aeon_phnom_penh", sample_records, scrape_date="2026-08-17"
    )
    assert s3_key == "parquet/month=2026-08/date=2026-08-17/aeon_phnom_penh.parquet"
    assert s3_key in fake.objects

    df = pd.read_parquet(io.BytesIO(fake.objects[s3_key]))
    assert len(df) == 2
    assert "item_description_raw" in df.columns
    assert "price" in df.columns
    assert "store_slug" in df.columns
    assert df["store_slug"].iloc[0] == "aeon_phnom_penh"


def test_parquet_archive_read_from_minio(monkeypatch):
    fake = _FakeMinio()
    monkeypatch.setattr("pipeline.parquet_archiver.MinioStorage", lambda: fake)

    archiver = ParquetArchiver()
    sample_records = [
        {"item_description_raw": "Jasmine Rice 5kg", "price": 4.50, "currency": "USD"},
    ]
    archiver.archive_records(
        "aeon_phnom_penh", sample_records, scrape_date="2026-08-17"
    )

    df = archiver.read_archive(store_slug="aeon_phnom_penh", date_str="2026-08-17")
    assert len(df) == 1
    assert df["price"].iloc[0] == 4.50


def test_parquet_archive_empty_records(monkeypatch):
    fake = _FakeMinio()
    monkeypatch.setattr("pipeline.parquet_archiver.MinioStorage", lambda: fake)

    archiver = ParquetArchiver()
    res = archiver.archive_records("store_empty", [], scrape_date="2026-08-17")
    assert res == ""
    assert fake.objects == {}
