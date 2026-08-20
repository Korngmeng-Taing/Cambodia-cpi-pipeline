"""
tests/test_bronze_validator.py
──────────────────────────────
Unit tests for the Bronze validation gate (Prompt 2).
boto3 (MinIO) and psycopg2 (Postgres) are mocked.
"""

import io
import sys
import types

import pandas as pd
import pytest

# Shims the real Airflow package (which is POSIX-only and fails to import on
# Windows) so the validator can be unit-tested on the host. In the Airflow
# container the real AirflowException is used.
_airflow = types.ModuleType("airflow")
_airflow_exc = types.ModuleType("airflow.exceptions")


class AirflowException(Exception):
    pass


_airflow_exc.AirflowException = AirflowException
_airflow.exceptions = _airflow_exc
sys.modules.setdefault("airflow", _airflow)
sys.modules.setdefault("airflow.exceptions", _airflow_exc)

from pipeline import bronze_validator as bv  # noqa: E402


class _FakeS3:
    def __init__(self, objects: dict[str, pd.DataFrame]):
        self.objects = objects
        self.prefixes = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"

        class _Paginator:
            def paginate(self, Bucket, Prefix):
                match = [
                    k
                    for k in self.owner
                    if k.startswith(Prefix) and k.endswith(".parquet")
                ]
                yield {"Contents": [{"Key": k} for k in match]}

        p = _Paginator()
        p.owner = self.objects
        return p

    def get_object(self, Bucket, Key):
        df = self.objects[Key]
        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow", index=False)
        buf.seek(0)
        return {"Body": buf}


class _FakeCursor:
    def __init__(self, avg):
        self.avg = avg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        self.calls = a

    def fetchone(self):
        return (self.avg,)


class _FakeConn:
    def __init__(self, avg):
        self.cur = _FakeCursor(avg)
        self.rows = []

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def close(self):
        pass


def _records_df(prices=(12500.0, 249.99, 8000.0)):
    return pd.DataFrame(
        {
            "raw_item_id": ["P1", "P2", "P3"],
            "raw_product_name": ["A", "B", "C"],
            "raw_price": list(prices),
            "raw_currency": ["KHR", "USD", "KHR"],
            "source_name": ["supermarket_a"] * 3,
        }
    )


def _patch(monkeypatch, objects, avg):
    fake_s3 = _FakeS3(objects)
    monkeypatch.setattr(bv, "_get_s3_client", lambda: fake_s3)
    monkeypatch.setattr(bv, "_get_db_connection", lambda: _FakeConn(avg))
    return fake_s3


def test_validator_passes(monkeypatch):
    key = "source=supermarket_a/scrape_date=2026-08-18/b.parquet"
    _patch(monkeypatch, {key: _records_df()}, avg=4.0)

    result = bv.validate_bronze_parquet("supermarket_a", "2026-08-18")
    assert result["status"] == "PASSED"
    assert result["row_count"] == 3


def test_validator_fails_empty_snapshot(monkeypatch):
    _patch(monkeypatch, {}, avg=2000.0)
    with pytest.raises(AirflowException, match="no parquet files"):
        bv.validate_bronze_parquet("supermarket_a", "2026-08-18")


def test_validator_fails_below_50pct_avg(monkeypatch):
    key = "source=supermarket_a/scrape_date=2026-08-18/b.parquet"
    _patch(monkeypatch, {key: _records_df()}, avg=10000.0)
    with pytest.raises(AirflowException, match="50% of 7-day average"):
        bv.validate_bronze_parquet("supermarket_a", "2026-08-18")


def test_validator_fails_on_negative_prices(monkeypatch):
    key = "source=supermarket_a/scrape_date=2026-08-18/b.parquet"
    _patch(monkeypatch, {key: _records_df(prices=(-5.0, 10.0, 20.0))}, avg=2000.0)
    with pytest.raises(AirflowException, match="negative"):
        bv.validate_bronze_parquet("supermarket_a", "2026-08-18")


def test_list_parquet_keys_filters_suffix(monkeypatch):
    key = "source=supermarket_a/scrape_date=2026-08-18/b.parquet"
    other = "source=supermarket_a/scrape_date=2026-08-18/summary.txt"
    objects = {key: _records_df(), other: _records_df()}
    _patch(monkeypatch, objects, avg=2000.0)
    keys = bv.list_parquet_keys("supermarket_a", "2026-08-18")
    assert keys == [key]
