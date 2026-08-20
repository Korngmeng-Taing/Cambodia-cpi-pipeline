"""
tests/test_minio_storage.py
───────────────────────────
Unit tests for the MinIO S3 object storage client (fail-loud, no local fallback).
"""

import io

import pytest

from pipeline.minio_storage import MinioStorage


class _FakeS3Client:
    """Minimal stand-in for a boto3 S3 client that stores objects in memory."""

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType="application/octet-stream"):
        self.objects[(Bucket, Key)] = io.BytesIO(Body)

    def get_object(self, Bucket, Key):
        body = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(body.getvalue())}


@pytest.fixture
def fake_storage():
    storage = MinioStorage(
        endpoint_url="http://fake:9000", bucket_name="cpi-bronze-test"
    )
    storage._client = _FakeS3Client()
    storage._client_initialized = True
    return storage


def test_minio_storage_put_and_get_json(fake_storage):
    sample_payload = [
        {"item_id": "test_1", "name": "Jasmine Rice 5kg", "price": 4.50},
        {"item_id": "test_2", "name": "Angkor Beer 330ml", "price": 0.85},
    ]

    uri = fake_storage.put_json("aeon_test", sample_payload, scrape_date="2026-08-17")
    assert uri == "s3://cpi-bronze-test/aeon_test/dt=2026-08-17/raw.json"

    stored = fake_storage.get_raw_records("aeon_test", scrape_date="2026-08-17")
    assert stored == sample_payload


def test_minio_storage_put_bytes_and_get_bytes(fake_storage):
    payload = b"\x00\x01binary-parquet-bytes"

    uri = fake_storage.put_bytes("parquet/archive.parquet", payload)
    assert uri == "s3://cpi-bronze-test/parquet/archive.parquet"

    assert fake_storage.get_bytes("parquet/archive.parquet") == payload


def test_minio_storage_raises_when_unreachable():
    storage = MinioStorage(
        endpoint_url="http://invalid-unreachable-host:9999",
        bucket_name="cpi-fallback",
    )

    sample_payload = {"test": "data", "status": "ok"}

    with pytest.raises(RuntimeError, match="MinIO unavailable"):
        storage.put_json("store_fallback", sample_payload, scrape_date="2026-08-17")

    with pytest.raises(RuntimeError, match="MinIO unavailable"):
        storage.get_raw_records("store_fallback", scrape_date="2026-08-17")
