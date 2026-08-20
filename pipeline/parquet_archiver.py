"""
pipeline/parquet_archiver.py
────────────────────────────
Parquet archiving service for raw scrape observations (Cold Storage Layer).

Stores immutable, append-only raw scrape archives in MinIO partitioned by:
    s3://cpi-bronze/parquet/month={YYYY-MM}/date={YYYY-MM-DD}/{store_slug}.parquet

No local filesystem storage: the Parquet payload is streamed straight to MinIO
and the DAG fails if MinIO is unavailable.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from pipeline.minio_storage import MinioStorage

log = logging.getLogger(__name__)


class ParquetArchiver:
    """
    Archives raw scrape JSON / dictionary records into partitioned Parquet files.
    """

    def archive_records(
        self,
        store_slug: str,
        records: list[dict[str, Any]],
        scrape_date: str | datetime | None = None,
    ) -> str:
        """
        Serializes raw records to a partitioned Parquet object and uploads it to
        MinIO.

        Returns:
            The S3 object key of the written Parquet archive (empty string when
            no records were provided).
        """
        if not records:
            log.warning("No records provided to archive for store '%s'.", store_slug)
            return ""

        if scrape_date is None:
            dt = datetime.now(UTC)
            date_str = dt.strftime("%Y-%m-%d")
        elif isinstance(scrape_date, datetime):
            dt = scrape_date
            date_str = dt.strftime("%Y-%m-%d")
        else:
            date_str = str(scrape_date)
            dt = datetime.strptime(date_str, "%Y-%m-%d")

        month_str = dt.strftime("%Y-%m")

        s3_key = (
            f"parquet/month={month_str}"
            f"/date={date_str}/{store_slug}.parquet"
        )

        df = pd.DataFrame(records)
        df["store_slug"] = store_slug
        df["archived_at"] = datetime.now(UTC).isoformat()
        df["scrape_date"] = date_str

        # pyarrow cannot serialize a struct with no child fields (e.g. attrs = {})
        empty_struct_cols = [
            col
            for col in df.columns
            if all(v == {} or v is None for v in df[col].tolist())
        ]
        if empty_struct_cols:
            log.info(
                "Dropping empty struct columns %s from archive for '%s'",
                empty_struct_cols,
                store_slug,
            )
            df = df.drop(columns=empty_struct_cols)

        # Serialize to bytes in memory, then stream to MinIO (no local file)
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False, compression="snappy")
        buffer.seek(0)

        minio_client = MinioStorage()
        minio_client.put_bytes(
            s3_key,
            buffer.getvalue(),
            content_type="application/vnd.apache.parquet",
        )
        log.info(
            "Archived %d records for '%s' on %s -> s3://%s/%s",
            len(df),
            store_slug,
            date_str,
            minio_client.bucket_name,
            s3_key,
        )
        return s3_key

    def read_archive(
        self,
        store_slug: str,
        date_str: str,
    ) -> pd.DataFrame:
        """
        Reads a single archived parquet object from MinIO into a DataFrame.
        """
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month_str = dt.strftime("%Y-%m")
        s3_key = (
            f"parquet/month={month_str}"
            f"/date={date_str}/{store_slug}.parquet"
        )
        try:
            raw = MinioStorage().get_bytes(s3_key)
        except RuntimeError:
            return pd.DataFrame()
        return pd.read_parquet(io.BytesIO(raw))
