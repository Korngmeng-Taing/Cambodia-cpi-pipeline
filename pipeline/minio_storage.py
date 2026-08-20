"""
pipeline/minio_storage.py
─────────────────────────
MinIO / S3 Object Storage Client for Raw Scrapes and Cold Parquet Archives.

Stores:
- Raw JSON Scrape Payloads: s3://cpi-bronze/{store_slug}/dt={YYYY-MM-DD}/raw.json
- Partitioned Parquet Archives: s3://cpi-bronze/parquet/month={YYYY-MM}/date={YYYY-MM-DD}/{store_slug}.parquet

Features:
- S3 / MinIO protocol with automatic bucket creation.
- Fail-loud behavior: no local filesystem fallback — if MinIO is unavailable,
  writes raise so the pipeline fails rather than persisting data locally.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "cpi-bronze")


class MinioStorage:
    """
    Manages raw scrape object storage on MinIO (S3-compatible).
    """

    def __init__(
        self,
        endpoint_url: str = MINIO_ENDPOINT,
        access_key: str = MINIO_ACCESS_KEY,
        secret_key: str = MINIO_SECRET_KEY,
        bucket_name: str = MINIO_BUCKET,
    ):
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self._client = None
        self._client_initialized = False

    def _ensure_client(self):
        """
        Lazily (re)initialises the S3 client. Cheap no-op after the first attempt,
        so constructing the storage object never blocks on network I/O.
        """
        if self._client_initialized:
            return
        self._client_initialized = True
        self._init_client()

    def _init_client(self):
        # Resolve localhost vs docker minio hostname
        endpoint = self.endpoint_url
        try:
            client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=5,
                    read_timeout=5,
                    retries={"max_attempts": 1},
                ),
                region_name="us-east-1",
            )
            # Test connectivity
            client.list_buckets()
            self._client = client
        except Exception:
            if "minio" in endpoint:
                alt_endpoint = endpoint.replace("minio:9000", "localhost:9000")
                try:
                    client = boto3.client(
                        "s3",
                        endpoint_url=alt_endpoint,
                        aws_access_key_id=self.access_key,
                        aws_secret_access_key=self.secret_key,
                        config=Config(
                            signature_version="s3v4",
                            connect_timeout=5,
                            read_timeout=5,
                            retries={"max_attempts": 1},
                        ),
                        region_name="us-east-1",
                    )
                    client.list_buckets()
                    self._client = client
                    self.endpoint_url = alt_endpoint
                except Exception as e:
                    log.warning(
                        "MinIO unavailable at %s: %s (no local fallback)",
                        alt_endpoint,
                        e,
                    )
                    self._client = None
            else:
                self._client = None

        if self._client:
            self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self.bucket_name)
                log.info("Created MinIO bucket: %s", self.bucket_name)
            except Exception as e:
                log.warning("Could not create MinIO bucket %s: %s", self.bucket_name, e)

    def put_json(
        self,
        store_slug: str,
        data: list[dict[str, Any]] | dict[str, Any],
        scrape_date: str | None = None,
    ) -> str:
        """
        Uploads raw JSON scrape records to MinIO S3 object storage.

        Object key follows the guide's raw layout:
            s3://{bucket}/{store_slug}/dt={YYYY-MM-DD}/raw.json
        """
        date_str = scrape_date or datetime.now(UTC).strftime("%Y-%m-%d")
        s3_key = f"{store_slug}/dt={date_str}/raw.json"
        body = json.dumps(data, indent=2, default=str).encode("utf-8")

        self._ensure_client()
        if not self._client:
            raise RuntimeError(
                f"MinIO unavailable ({self.endpoint_url}); refusing to store raw "
                f"JSON for {store_slug} locally"
            )
        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=body,
                ContentType="application/json",
            )
            uri = f"s3://{self.bucket_name}/{s3_key}"
            log.info("Stored raw JSON scrape in MinIO: %s", uri)
            return uri
        except Exception as exc:
            raise RuntimeError(f"MinIO put_object failed for {s3_key}: {exc}") from exc

    def put_bytes(
        self,
        s3_key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Uploads an in-memory byte payload (e.g. serialized Parquet) to MinIO.
        """
        self._ensure_client()
        if not self._client:
            raise RuntimeError(
                f"MinIO unavailable ({self.endpoint_url}); refusing to store "
                f"{s3_key} locally"
            )
        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=body,
                ContentType=content_type,
            )
            uri = f"s3://{self.bucket_name}/{s3_key}"
            log.info("Uploaded bytes to MinIO -> %s", uri)
            return uri
        except Exception as exc:
            raise RuntimeError(f"MinIO put_bytes failed for {s3_key}: {exc}") from exc

    def put_file(
        self,
        local_file_path: str | Path,
        s3_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Uploads an existing local file (e.g. Parquet) to MinIO.
        """
        path = Path(local_file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {local_file_path}")

        self._ensure_client()
        if not self._client:
            raise RuntimeError(
                f"MinIO unavailable ({self.endpoint_url}); refusing to store "
                f"{s3_key} locally"
            )
        try:
            self._client.upload_file(
                str(path),
                self.bucket_name,
                s3_key,
                ExtraArgs={"ContentType": content_type},
            )
            uri = f"s3://{self.bucket_name}/{s3_key}"
            log.info("Uploaded %s to MinIO -> %s", path.name, uri)
            return uri
        except Exception as exc:
            raise RuntimeError(f"MinIO upload_file failed for {s3_key}: {exc}") from exc

    def get_bytes(self, s3_key: str) -> bytes:
        """
        Downloads and returns the raw bytes of an object from MinIO.
        """
        self._ensure_client()
        if not self._client:
            raise RuntimeError(
                f"MinIO unavailable ({self.endpoint_url}); cannot read {s3_key}"
            )
        try:
            resp = self._client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return resp["Body"].read()
        except Exception as exc:
            raise RuntimeError(f"MinIO get_object failed for {s3_key}: {exc}") from exc

    def get_json(self, s3_key: str) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Downloads and parses JSON object from MinIO.
        """
        raw = self.get_bytes(s3_key)
        return json.loads(raw.decode("utf-8"))

    def get_raw_records(
        self,
        store_slug: str,
        scrape_date: str | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Convenience loader for the raw scrape snapshot of a source/date.

        Key: s3://{bucket}/{store_slug}/dt={YYYY-MM-DD}/raw.json
        """
        date_str = scrape_date or datetime.now(UTC).strftime("%Y-%m-%d")
        return self.get_json(f"{store_slug}/dt={date_str}/raw.json")
