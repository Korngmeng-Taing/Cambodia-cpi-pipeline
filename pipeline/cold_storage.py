"""
pipeline/cold_storage.py
────────────────────────
Cold Storage Parquet Offloading Engine for Cambodia CPI Warehouse.

Automatically identifies completed historical monthly partitions in:
  - bronze.raw_prices (RANGE by scraped_at)
  - silver.clean_store_prices (RANGE by scrape_date)

Extracts partition microdata, streams it into high-performance columnar
compressed Apache Parquet (ZSTD / Snappy) files, verifies data integrity
via cryptographic SHA-256 checksums, and catalogs metadata in PostgreSQL
(ops.cold_storage_catalog).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.config import get_db_connection

log = logging.getLogger(__name__)

DEFAULT_COLD_STORAGE_DIR = Path(
    os.getenv("CPI_COLD_STORAGE_DIR", Path(__file__).resolve().parent.parent / "data" / "cold_storage")
)


def get_cold_storage_dir() -> Path:
    """Returns the base directory for cold storage Parquet files, creating it if needed."""
    storage_dir = Path(os.getenv("CPI_COLD_STORAGE_DIR", DEFAULT_COLD_STORAGE_DIR))
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def resolve_cold_storage_path(stored_path: Path | str, base_dir: Path | None = None) -> Path:
    """Resolves a catalog path (relative or legacy absolute) against the environment's cold storage base dir."""
    if base_dir is None:
        base_dir = get_cold_storage_dir()

    raw = str(stored_path).strip()
    try:
        p = Path(raw)
        if p.exists():
            return p
    except Exception:
        pass

    candidate = base_dir / raw
    if candidate.exists():
        return candidate

    norm = raw.replace("\\", "/")
    marker = "/cold_storage/"
    if marker in norm:
        rel_suffix = norm.split(marker, 1)[1]
        alt_cand = base_dir / rel_suffix
        if alt_cand.exists():
            return alt_cand
        return alt_cand

    return candidate


def calculate_file_sha256(filepath: Path | str) -> str:
    """Computes the SHA-256 checksum of a file in 64KB chunks."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def init_cold_storage_catalog(conn: Any = None) -> None:
    """Ensures the ops schema and ops.cold_storage_catalog table exist in PostgreSQL."""
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS ops;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ops.cold_storage_catalog (
                    id SERIAL PRIMARY KEY,
                    schema_name VARCHAR(64) NOT NULL,
                    parent_table VARCHAR(64) NOT NULL,
                    partition_name VARCHAR(128) NOT NULL,
                    year INT NOT NULL,
                    month INT NOT NULL,
                    parquet_path TEXT NOT NULL,
                    file_size_bytes BIGINT NOT NULL,
                    row_count BIGINT NOT NULL,
                    sha256_checksum VARCHAR(64) NOT NULL,
                    compression VARCHAR(32) NOT NULL DEFAULT 'zstd',
                    min_timestamp TIMESTAMPTZ,
                    max_timestamp TIMESTAMPTZ,
                    exported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    status VARCHAR(32) NOT NULL DEFAULT 'verified',
                    CONSTRAINT uq_cold_storage_partition UNIQUE (schema_name, partition_name)
                );

                CREATE INDEX IF NOT EXISTS idx_cold_storage_table_period 
                    ON ops.cold_storage_catalog (schema_name, parent_table, year, month);

                CREATE INDEX IF NOT EXISTS idx_cold_storage_status 
                    ON ops.cold_storage_catalog (status);
                """
            )
            conn.commit()
            log.info("ops.cold_storage_catalog table verified/created.")
    finally:
        if should_close:
            conn.close()


def get_offloadable_partitions(
    schema_names: list[str] | None = None,
    months_threshold: int = 1,
    force: bool = False,
    conn: Any = None,
) -> list[dict[str, Any]]:
    """Discovers closed monthly partitions eligible for cold storage offloading.

    A partition is eligible if:
      1. Its year and month are strictly before the current month (or older than months_threshold).
      2. It contains > 0 rows.
      3. It has not already been successfully offloaded to ops.cold_storage_catalog (unless force=True).
    """
    if schema_names is None:
        schema_names = ["bronze", "silver"]

    init_cold_storage_catalog(conn=conn)

    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    candidates = []
    today = date.today()

    # Calculate cutoff year and month
    cutoff_month = today.month - months_threshold
    cutoff_year = today.year
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1

    try:
        with conn.cursor() as cur:
            # Query all partition children belonging to bronze or silver tables
            cur.execute(
                """
                SELECT 
                    n.nspname AS schema_name,
                    parent.relname AS parent_table,
                    child.relname AS partition_name
                FROM pg_inherits i
                JOIN pg_class parent ON i.inhparent = parent.oid
                JOIN pg_class child ON i.inhrelid = child.oid
                JOIN pg_namespace n ON n.oid = parent.relnamespace
                WHERE n.nspname = ANY(%s)
                  AND parent.relname IN ('raw_prices', 'clean_store_prices')
                ORDER BY n.nspname, parent.relname, child.relname;
                """,
                (schema_names,),
            )
            rows = cur.fetchall()

            for schema_name, parent_table, partition_name in rows:
                # Match naming pattern like raw_prices_2026_08 or clean_store_prices_2026_08
                match = re.search(r"(\d{4})_(\d{2})$", partition_name)
                if not match:
                    continue

                part_year = int(match.group(1))
                part_month = int(match.group(2))

                # Check if it is older than or equal to cutoff period
                if (part_year, part_month) > (cutoff_year, cutoff_month):
                    continue  # Still current or future month

                # Check if already exported and verified
                if not force:
                    cur.execute(
                        """
                        SELECT status, sha256_checksum, parquet_path 
                        FROM ops.cold_storage_catalog
                        WHERE schema_name = %s AND partition_name = %s;
                        """,
                        (schema_name, partition_name),
                    )
                    existing = cur.fetchone()
                    if existing and existing[0] in ("verified", "archived"):
                        # Check if physical file exists via portable path resolver
                        file_path = resolve_cold_storage_path(existing[2])
                        if file_path.exists():
                            log.debug("Partition %s.%s already offloaded and verified.", schema_name, partition_name)
                            continue

                # Check row count
                cur.execute(f"SELECT COUNT(*) FROM {schema_name}.{partition_name};")
                row_count = cur.fetchone()[0]
                if row_count == 0:
                    log.debug("Partition %s.%s is empty. Skipping.", schema_name, partition_name)
                    continue

                # Determine timestamp / date column
                date_col = "scraped_at" if parent_table == "raw_prices" else "scrape_date"
                cur.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM {schema_name}.{partition_name};")
                min_dt, max_dt = cur.fetchone()

                candidates.append(
                    {
                        "schema_name": schema_name,
                        "parent_table": parent_table,
                        "partition_name": partition_name,
                        "year": part_year,
                        "month": part_month,
                        "row_count": row_count,
                        "min_dt": min_dt,
                        "max_dt": max_dt,
                    }
                )
    finally:
        if should_close:
            conn.close()

    return candidates


def _pg_type_to_arrow(data_type: str) -> pa.DataType:
    """Maps PostgreSQL data types to PyArrow data types."""
    dt = data_type.lower()
    if "int8" in dt or "bigint" in dt:
        return pa.int64()
    elif "int4" in dt or "integer" in dt:
        return pa.int32()
    elif "int2" in dt or "smallint" in dt:
        return pa.int16()
    elif any(t in dt for t in ("numeric", "decimal", "double", "real", "float")):
        return pa.float64()
    elif "bool" in dt:
        return pa.bool_()
    elif "date" in dt:
        return pa.date32()
    elif "timestamp with time zone" in dt or "timestamptz" in dt:
        return pa.timestamp("us", tz="UTC")
    elif "timestamp" in dt:
        return pa.timestamp("us")
    elif "uuid" in dt:
        return pa.string()
    elif "json" in dt:
        return pa.string()
    return pa.string()


def get_table_arrow_schema(schema_name: str, table_name: str, conn: Any) -> pa.Schema:
    """Retrieves explicit PyArrow schema from PostgreSQL column types."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = %s AND table_name = %s 
            ORDER BY ordinal_position;
            """,
            (schema_name, table_name),
        )
        cols = cur.fetchall()
        if not cols:
            parent = "raw_prices" if "raw_prices" in table_name else "clean_store_prices"
            cur.execute(
                """
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = %s AND table_name = %s 
                ORDER BY ordinal_position;
                """,
                (schema_name, parent),
            )
            cols = cur.fetchall()

    fields = [pa.field(col[0], _pg_type_to_arrow(col[1])) for col in cols]
    return pa.schema(fields)


def _serialize_cell_for_arrow(val: Any) -> Any:
    """Prepares Python types for Arrow serialization without losing structure."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False, default=str)
    if isinstance(val, Decimal):
        return float(val)
    return val


def export_partition_to_parquet(
    schema_name: str,
    partition_name: str,
    target_dir: Path | None = None,
    compression: str = "zstd",
    batch_size: int = 50000,
    conn: Any = None,
) -> dict[str, Any]:
    """Streams a database partition into a compressed columnar Parquet file.

    Args:
        schema_name: Schema containing partition ('bronze' or 'silver').
        partition_name: Name of the partition table (e.g. 'raw_prices_2026_08').
        target_dir: Base directory for cold storage.
        compression: Parquet compression codec ('zstd' or 'snappy').
        batch_size: Number of records per streaming chunk.
        conn: Optional DB connection.

    Returns:
        dict with export metrics, file path, and SHA-256 checksum.
    """
    if target_dir is None:
        target_dir = get_cold_storage_dir()

    init_cold_storage_catalog(conn=conn)

    # Extract parent table, year, and month
    match = re.search(r"^(.*?)_(\d{4})_(\d{2})$", partition_name)
    if match:
        parent_table = match.group(1)
        year = int(match.group(2))
        month = int(match.group(3))
    else:
        parent_table = "raw_prices" if "raw_prices" in partition_name else "clean_store_prices"
        year = date.today().year
        month = date.today().month

    # Destination directory structure: {target_dir}/{schema_name}/{parent_table}/year=YYYY/month=MM/
    dest_dir = target_dir / schema_name / parent_table / f"year={year}" / f"month={month:02d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = dest_dir / f"{partition_name}.parquet"
    temp_path = dest_dir / f"{partition_name}.tmp.parquet"

    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        date_col = "scraped_at" if "raw_prices" in partition_name else "scrape_date"
        with conn.cursor() as cur:
            # Query bounds and total count
            cur.execute(f"SELECT COUNT(*), MIN({date_col}), MAX({date_col}) FROM {schema_name}.{partition_name};")
            total_db_rows, min_dt, max_dt = cur.fetchone()

        if total_db_rows == 0:
            return {
                "status": "skipped",
                "reason": "partition_is_empty",
                "partition_name": partition_name,
                "rows": 0,
            }

        log.info(
            "Exporting %s.%s (%d rows) to Parquet (compression=%s)...",
            schema_name,
            partition_name,
            total_db_rows,
            compression,
        )

        writer: pq.ParquetWriter | None = None
        rows_exported = 0

        # Introspect table schema to prevent column type drift across batches
        table_arrow_schema = get_table_arrow_schema(schema_name, partition_name, conn)

        # Use server-side named cursor to stream large partitions with minimal RAM
        cursor_name = f"cur_cold_{schema_name}_{partition_name}"
        with conn.cursor(name=cursor_name) as cur:
            cur.itersize = batch_size
            cur.execute(f"SELECT * FROM {schema_name}.{partition_name};")

            col_names: list[str] | None = None

            while True:
                batch = cur.fetchmany(batch_size)
                if not batch:
                    break

                if col_names is None:
                    col_names = [desc[0] for desc in cur.description]

                # Prepare column-oriented dictionary
                col_data: dict[str, list[Any]] = {col: [] for col in col_names}
                for row in batch:
                    for i, col in enumerate(col_names):
                        col_data[col].append(_serialize_cell_for_arrow(row[i]))

                # Convert to Arrow Table with guaranteed static schema
                arrow_batch = pa.Table.from_pydict(col_data, schema=table_arrow_schema)

                if writer is None:
                    writer = pq.ParquetWriter(
                        str(temp_path),
                        table_arrow_schema,
                        compression=compression,
                        use_dictionary=True,
                    )

                writer.write_table(arrow_batch)
                rows_exported += len(batch)
                log.debug("Streamed %d / %d rows to %s", rows_exported, total_db_rows, temp_path.name)

        if writer is not None:
            writer.close()

        # Atomic replace of temporary parquet file
        if temp_path.exists():
            if parquet_path.exists():
                parquet_path.unlink()
            temp_path.rename(parquet_path)

        # Integrity Validation: Verify row count in Parquet footer
        meta = pq.read_metadata(str(parquet_path))
        parquet_rows = meta.num_rows
        if parquet_rows != total_db_rows:
            raise ValueError(
                f"Integrity check failed for {parquet_path}: "
                f"database had {total_db_rows} rows, but Parquet contains {parquet_rows} rows."
            )

        file_size = parquet_path.stat().st_size
        sha256 = calculate_file_sha256(parquet_path)
        rel_parquet_path = f"{schema_name}/{parent_table}/year={year}/month={month:02d}/{partition_name}.parquet"

        # Record portable relative path in ops.cold_storage_catalog
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops.cold_storage_catalog (
                    schema_name, parent_table, partition_name, year, month,
                    parquet_path, file_size_bytes, row_count, sha256_checksum,
                    compression, min_timestamp, max_timestamp, exported_at, status
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, NOW(), 'verified'
                )
                ON CONFLICT (schema_name, partition_name) DO UPDATE SET
                    parquet_path = EXCLUDED.parquet_path,
                    file_size_bytes = EXCLUDED.file_size_bytes,
                    row_count = EXCLUDED.row_count,
                    sha256_checksum = EXCLUDED.sha256_checksum,
                    compression = EXCLUDED.compression,
                    min_timestamp = EXCLUDED.min_timestamp,
                    max_timestamp = EXCLUDED.max_timestamp,
                    exported_at = NOW(),
                    status = 'verified';
                """,
                (
                    schema_name,
                    parent_table,
                    partition_name,
                    year,
                    month,
                    rel_parquet_path,
                    file_size,
                    parquet_rows,
                    sha256,
                    compression,
                    min_dt,
                    max_dt,
                ),
            )
            conn.commit()

        log.info(
            "Successfully offloaded %s.%s -> %s (Size: %.2f MB, Rows: %d, SHA-256: %s...)",
            schema_name,
            partition_name,
            parquet_path.name,
            file_size / (1024 * 1024),
            parquet_rows,
            sha256[:12],
        )

        return {
            "status": "success",
            "schema_name": schema_name,
            "partition_name": partition_name,
            "parent_table": parent_table,
            "year": year,
            "month": month,
            "parquet_path": str(parquet_path),
            "file_size_bytes": file_size,
            "row_count": parquet_rows,
            "sha256": sha256,
            "compression": compression,
        }

    except Exception as e:
        log.error("Failed to export partition %s.%s: %s", schema_name, partition_name, e)
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise
    finally:
        if should_close:
            conn.close()


def verify_cold_partition(parquet_path: Path | str, expected_sha256: str | None = None) -> bool:
    """Verifies that an offloaded Parquet file is readable and matches its SHA-256."""
    path = resolve_cold_storage_path(parquet_path)
    if not path.exists():
        log.error("Cold partition file does not exist: %s", path)
        return False

    if expected_sha256:
        actual_sha256 = calculate_file_sha256(path)
        if actual_sha256 != expected_sha256:
            log.error("Checksum mismatch for %s: expected %s, got %s", path, expected_sha256, actual_sha256)
            return False

    try:
        meta = pq.read_metadata(str(path))
        if meta.num_rows <= 0:
            log.warning("Parquet file %s has 0 rows.", path)
            return False
        return True
    except Exception as err:
        log.error("Parquet validation error on %s: %s", path, err)
        return False


def read_cold_partition(
    schema_name: str,
    parent_table: str,
    year: int,
    month: int,
    columns: list[str] | None = None,
    target_dir: Path | None = None,
) -> pd.DataFrame:
    """Reads an offloaded historical partition directly into a Pandas DataFrame from Parquet.

    Bypasses PostgreSQL completely for fast, zero-overhead analytical workloads.
    """
    if target_dir is None:
        target_dir = get_cold_storage_dir()

    expected_path = target_dir / schema_name / parent_table / f"year={year}" / f"month={month:02d}" / f"{parent_table}_{year:04d}_{month:02d}.parquet"

    if not expected_path.exists():
        # Check alternative naming
        alt_path = target_dir / schema_name / parent_table / f"year={year}" / f"month={month:02d}" / f"{parent_table}_part_{year:04d}_{month:02d}.parquet"
        if alt_path.exists():
            expected_path = alt_path
        else:
            raise FileNotFoundError(f"Cold storage partition not found at {expected_path}")

    log.info("Reading cold storage partition from %s (columns=%s)...", expected_path, columns)
    table = pq.read_table(str(expected_path), columns=columns)
    return table.to_pandas()


def list_cold_catalog(conn: Any = None) -> list[dict[str, Any]]:
    """Retrieves all registered cold storage partitions from ops.cold_storage_catalog."""
    init_cold_storage_catalog(conn=conn)

    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    id, schema_name, parent_table, partition_name, year, month,
                    parquet_path, file_size_bytes, row_count, sha256_checksum,
                    compression, min_timestamp, max_timestamp, exported_at, status
                FROM ops.cold_storage_catalog
                ORDER BY schema_name, parent_table, year, month;
                """
            )
            col_names = [desc[0] for desc in cur.description]
            records = []
            for row in cur.fetchall():
                records.append(dict(zip(col_names, row, strict=False)))
            return records
    finally:
        if should_close:
            conn.close()


def run_cold_storage_offloading(
    months_threshold: int = 1,
    compression: str = "zstd",
    force: bool = False,
    conn: Any = None,
) -> dict[str, Any]:
    """Main automated workflow: finds candidate historical partitions and offloads them to Parquet."""
    candidates = get_offloadable_partitions(
        months_threshold=months_threshold,
        force=force,
        conn=conn,
    )

    if not candidates:
        log.info("No closed partitions eligible for cold storage offloading.")
        return {
            "status": "success",
            "message": "no_eligible_partitions",
            "offloaded_count": 0,
            "partitions": [],
        }

    log.info("Found %d eligible partitions for cold storage offloading: %s", len(candidates), [c["partition_name"] for c in candidates])

    results = []
    for cand in candidates:
        res = export_partition_to_parquet(
            schema_name=cand["schema_name"],
            partition_name=cand["partition_name"],
            compression=compression,
            conn=conn,
        )
        results.append(res)

    total_bytes = sum(r.get("file_size_bytes", 0) for r in results)
    total_rows = sum(r.get("row_count", 0) for r in results)

    log.info(
        "Cold storage offloading complete. Offloaded %d partitions, %d rows, %.2f MB.",
        len(results),
        total_rows,
        total_bytes / (1024 * 1024),
    )

    return {
        "status": "success",
        "offloaded_count": len(results),
        "total_rows": total_rows,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "partitions": results,
    }


def main() -> None:
    """CLI Entrypoint for Cold Storage Parquet Offloading."""
    parser = argparse.ArgumentParser(description="Cambodia CPI Cold Storage Parquet Offloader")
    parser.add_argument("--offload-all", action="store_true", help="Offload all eligible closed partitions")
    parser.add_argument("--partition", type=str, help="Specific partition to offload (e.g. bronze.raw_prices_2026_08)")
    parser.add_argument("--months-threshold", type=int, default=1, help="Age in months to consider closed (default: 1)")
    parser.add_argument("--compression", type=str, default="zstd", choices=["zstd", "snappy"], help="Compression codec")
    parser.add_argument("--force", action="store_true", help="Re-export even if already verified in catalog")
    parser.add_argument("--list-catalog", action="store_true", help="List all cataloged cold storage partitions")
    parser.add_argument("--verify", type=str, help="Verify integrity of a Parquet file path")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.list_catalog:
        catalog = list_cold_catalog()
        print(f"\n--- Cold Storage Catalog ({len(catalog)} entries) ---")
        for entry in catalog:
            size_mb = entry["file_size_bytes"] / (1024 * 1024)
            print(
                f"[{entry['status'].upper()}] {entry['schema_name']}.{entry['partition_name']} "
                f"| Rows: {entry['row_count']:,} | Size: {size_mb:.2f} MB "
                f"| Path: {entry['parquet_path']}"
            )
        return

    if args.verify:
        is_valid = verify_cold_partition(args.verify)
        print(f"Parquet file {args.verify} valid: {is_valid}")
        return

    if args.partition:
        parts = args.partition.split(".")
        if len(parts) == 2:
            schema_name, part_name = parts
        else:
            schema_name = "bronze" if "raw_prices" in args.partition else "silver"
            part_name = args.partition
        res = export_partition_to_parquet(
            schema_name=schema_name,
            partition_name=part_name,
            compression=args.compression,
        )
        print(f"Export result: {res}")
        return

    if args.offload_all:
        res = run_cold_storage_offloading(
            months_threshold=args.months_threshold,
            compression=args.compression,
            force=args.force,
        )
        print(f"Offloading result: {res}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
