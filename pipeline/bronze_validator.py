"""
pipeline/bronze_validator.py
────────────────────────────
Airflow Bronze Validation Task for Parquet snapshots uploaded by the Playwright
scrapers (see scrapers/playwright_to_minio.py).

The validator runs after a source's parquet snapshot lands in MinIO and enforces
the Bronze quality gate BEFORE data flows to Silver:

    1. Row count  > 0                                     (empty snapshot fails)
    2. Row count >= 50% of the last-7-day average         (truncated scrape fails)
    3. raw_price has no nulls and no negative values      (price sanity fails)

On success a stats row is upserted into staging.bronze_ingestion_stats; on any
failure an AirflowException is raised so the DAG stops and retries.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3
import pandas as pd
import psycopg2
from airflow.exceptions import AirflowException
from botocore.client import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "cpi-bronze")

MIN_ROW_FRACTION_OF_7D_AVG = 0.5
STATS_LOOKBACK_DAYS = 7


def _get_db_connection():
    conn_str = os.getenv(
        "CPI_DATABASE_URL",
        "postgresql://cpi_user:cpi_pass@postgres:5432/cpi_db",
    )
    conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
    try:
        return psycopg2.connect(conn_str)
    except psycopg2.OperationalError:
        if "postgres" in conn_str:
            alt = conn_str.replace("postgres:5432", "localhost:5432")
        else:
            alt = conn_str.replace("localhost:5432", "postgres:5432")
        return psycopg2.connect(alt)


def _get_s3_client() -> boto3.client:
    endpoint = MINIO_ENDPOINT
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}),
            region_name="us-east-1",
        )
        client.list_buckets()
        return client
    except Exception:
        if "minio" not in endpoint:
            raise
        alt = endpoint.replace("minio:9000", "localhost:9000")
        log.warning("MinIO unreachable at %s; retrying %s", endpoint, alt)
        client = boto3.client(
            "s3",
            endpoint_url=alt,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}),
            region_name="us-east-1",
        )
        client.list_buckets()
        return client


def list_parquet_keys(source_name: str, scrape_date: str) -> list[str]:
    """Lists today's partition keys: source={source_name}/scrape_date={date}/*.parquet."""
    prefix = f"source={source_name}/scrape_date={scrape_date}/"
    client = _get_s3_client()
    keys: list[str] = []
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=MINIO_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".parquet"):
                    keys.append(obj["Key"])
    except ClientError as exc:
        raise AirflowException(f"Failed to list MinIO objects under '{prefix}': {exc}") from exc
    log.info("Found %d parquet file(s) for %s on %s", len(keys), source_name, scrape_date)
    return keys


def _fetch_avg_row_count_7d(source_name: str, scrape_date: str) -> float:
    """Average row count of successful snapshots over the previous 7 days."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(AVG(row_count), 0)
                FROM staging.bronze_ingestion_stats
                WHERE source_name = %s
                  AND status = 'PASSED'
                  AND scrape_date >= %s::DATE - INTERVAL '%s days'
                  AND scrape_date < %s::DATE
                """,
                (source_name, scrape_date, STATS_LOOKBACK_DAYS, scrape_date),
            )
            return float(cur.fetchone()[0])
    finally:
        conn.close()


def _read_snapshot_stats(s3_keys: list[str]) -> dict[str, Any]:
    """Reads row counts and raw_price sanity from the parquet files via pyarrow."""
    total_rows = 0
    price_nulls = 0
    price_negatives = 0
    client = _get_s3_client()
    for key in s3_keys:
        obj = client.get_object(Bucket=MINIO_BUCKET, Key=key)
        df = pd.read_parquet(obj["Body"], engine="pyarrow")
        total_rows += len(df)
        if "raw_price" in df.columns:
            price_nulls += int(df["raw_price"].isna().sum())
            price_negatives += int((df["raw_price"] < 0).sum())
    return {
        "row_count": total_rows,
        "price_nulls": price_nulls,
        "price_negatives": price_negatives,
    }


def _upsert_stats(source_name: str, scrape_date: str, stats: dict[str, Any], status: str, message: str, s3_keys: list[str]) -> None:
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO staging.bronze_ingestion_stats (
                    source_name, scrape_date, object_key, row_count,
                    avg_row_count_7d, price_nulls, price_negatives, status, validation_message
                ) VALUES (%s, %s::DATE, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_name, scrape_date) DO UPDATE
                SET object_key = EXCLUDED.object_key,
                    row_count = EXCLUDED.row_count,
                    avg_row_count_7d = EXCLUDED.avg_row_count_7d,
                    price_nulls = EXCLUDED.price_nulls,
                    price_negatives = EXCLUDED.price_negatives,
                    status = EXCLUDED.status,
                    validation_message = EXCLUDED.validation_message,
                    created_at = NOW()
                """,
                (
                    source_name,
                    scrape_date,
                    s3_keys[0] if s3_keys else None,
                    stats["row_count"],
                    stats["avg_row_count_7d"],
                    stats["price_nulls"],
                    stats["price_negatives"],
                    status,
                    message,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def validate_bronze_parquet(source_name: str, scrape_date: str) -> dict[str, Any]:
    """
    Validates today's Bronze Parquet snapshot for a source.

    Raises AirflowException (fails the Airflow task) on any rule violation;
    otherwise returns a summary dict with the stats row inserted.
    """
    s3_keys = list_parquet_keys(source_name, scrape_date)
    if not s3_keys:
        raise AirflowException(
            f"Bronze validation FAILED for {source_name} on {scrape_date}: "
            f"no parquet files under source={source_name}/scrape_date={scrape_date}/"
        )

    stats = _read_snapshot_stats(s3_keys)
    avg_7d = _fetch_avg_row_count_7d(source_name, scrape_date)
    stats["avg_row_count_7d"] = avg_7d

    errors: list[str] = []

    if stats["row_count"] == 0:
        errors.append("row count is 0")

    if avg_7d > 0 and stats["row_count"] < avg_7d * MIN_ROW_FRACTION_OF_7D_AVG:
        errors.append(
            f"row count {stats['row_count']} < 50% of 7-day average {avg_7d:.0f}"
        )

    if stats["price_nulls"] > 0:
        errors.append(f"raw_price contains {stats['price_nulls']} null value(s)")

    if stats["price_negatives"] > 0:
        errors.append(f"raw_price contains {stats['price_negatives']} negative value(s)")

    if errors:
        message = "; ".join(errors)
        log.error("Bronze validation FAILED for %s on %s: %s", source_name, scrape_date, message)
        _upsert_stats(source_name, scrape_date, stats, "FAILED", message, s3_keys)
        raise AirflowException(
            f"Bronze validation FAILED for {source_name} on {scrape_date}: {message}"
        )

    message = f"OK: {stats['row_count']} rows, avg_7d={avg_7d:.0f}"
    _upsert_stats(source_name, scrape_date, stats, "PASSED", message, s3_keys)
    log.info("Bronze validation PASSED for %s on %s: %s", source_name, scrape_date, message)
    return {"source_name": source_name, "scrape_date": scrape_date, "status": "PASSED", **stats}
