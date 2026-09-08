"""
tests/test_cold_storage.py
──────────────────────────
Unit tests for pipeline.cold_storage.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.cold_storage import (
    _serialize_cell_for_arrow,
    calculate_file_sha256,
    get_cold_storage_dir,
    get_offloadable_partitions,
    init_cold_storage_catalog,
    read_cold_partition,
    resolve_cold_storage_path,
    verify_cold_partition,
)


def test_serialize_cell_for_arrow():
    """Verify serialization of JSONB dicts, Decimals, and basic types for PyArrow."""
    assert _serialize_cell_for_arrow(None) is None
    assert _serialize_cell_for_arrow("hello") == "hello"
    assert _serialize_cell_for_arrow(123) == 123
    assert _serialize_cell_for_arrow(Decimal("45.67")) == 45.67

    sample_dict = {"key": "value", "count": 10}
    serialized = _serialize_cell_for_arrow(sample_dict)
    assert isinstance(serialized, str)
    assert json.loads(serialized) == sample_dict

    sample_list = [1, 2, "item"]
    serialized_list = _serialize_cell_for_arrow(sample_list)
    assert isinstance(serialized_list, str)
    assert json.loads(serialized_list) == sample_list


def test_calculate_file_sha256(tmp_path: Path):
    """Verify SHA-256 computation on test files."""
    test_file = tmp_path / "sample.txt"
    content = b"Cambodia CPI Pipeline Cold Storage Test"
    test_file.write_bytes(content)

    import hashlib
    expected_sha = hashlib.sha256(content).hexdigest()
    actual_sha = calculate_file_sha256(test_file)
    assert actual_sha == expected_sha


def test_get_cold_storage_dir(monkeypatch, tmp_path: Path):
    """Verify environment variable override and directory auto-creation."""
    custom_dir = tmp_path / "custom_cold"
    monkeypatch.setenv("CPI_COLD_STORAGE_DIR", str(custom_dir))

    d = get_cold_storage_dir()
    assert d == custom_dir
    assert custom_dir.exists()
    assert custom_dir.is_dir()


def test_init_cold_storage_catalog():
    """Verify catalog initialization creates schema and table idempotently."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    init_cold_storage_catalog(conn=mock_conn)

    mock_cur.execute.assert_any_call("CREATE SCHEMA IF NOT EXISTS ops;")
    mock_conn.commit.assert_called_once()


def test_verify_cold_partition(tmp_path: Path):
    """Verify Parquet integrity checking and checksum verification."""
    parquet_path = tmp_path / "test.parquet"
    schema = pa.schema([("id", pa.int64()), ("price", pa.float64())])
    tbl = pa.Table.from_arrays([pa.array([1, 2]), pa.array([10.5, 20.0])], schema=schema)
    pq.write_table(tbl, str(parquet_path), compression="zstd")

    # True checksum
    correct_sha = calculate_file_sha256(parquet_path)
    assert verify_cold_partition(parquet_path, expected_sha256=correct_sha) is True

    # False checksum
    assert verify_cold_partition(parquet_path, expected_sha256="wrong_checksum") is False

    # Non-existent file
    assert verify_cold_partition(tmp_path / "non_existent.parquet") is False


def test_get_offloadable_partitions():
    """Verify discovery of candidate historical partitions."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Mock DB returning partitions
    mock_cur.fetchall.return_value = [
        ("bronze", "raw_prices", "raw_prices_2026_08"),
        ("bronze", "raw_prices", "raw_prices_2099_01"),  # future, should skip
    ]

    # For existing catalog check: None (not yet exported)
    # For count: 50000 rows
    # For min/max date: timestamps
    mock_cur.fetchone.side_effect = [
        None,  # catalog check
        (50000,),  # count(*)
        ("2026-08-01 00:00:00", "2026-08-31 23:59:59"),  # min/max
    ]

    candidates = get_offloadable_partitions(
        schema_names=["bronze"],
        months_threshold=1,
        conn=mock_conn,
    )

    assert len(candidates) == 1
    assert candidates[0]["partition_name"] == "raw_prices_2026_08"
    assert candidates[0]["year"] == 2026
    assert candidates[0]["month"] == 8
    assert candidates[0]["row_count"] == 50000


def test_read_cold_partition(tmp_path: Path):
    """Verify loading cold partition into pandas from Parquet file structure."""
    target_dir = tmp_path / "cold_storage"
    part_dir = target_dir / "bronze" / "raw_prices" / "year=2026" / "month=08"
    part_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = part_dir / "raw_prices_2026_08.parquet"

    schema = pa.schema([("id", pa.int64()), ("price", pa.float64())])
    tbl = pa.Table.from_arrays([pa.array([101, 102]), pa.array([15.0, 25.5])], schema=schema)
    pq.write_table(tbl, str(parquet_path), compression="zstd")

    df = read_cold_partition(
        schema_name="bronze",
        parent_table="raw_prices",
        year=2026,
        month=8,
        target_dir=target_dir,
    )

    assert len(df) == 2
    assert list(df["id"]) == [101, 102]
    assert list(df["price"]) == [15.0, 25.5]


def test_resolve_cold_storage_path(tmp_path: Path):
    """Verify relative and legacy cross-platform path resolution."""
    base_dir = tmp_path / "data" / "cold_storage"
    target_file = base_dir / "bronze" / "raw_prices" / "test.parquet"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.touch()

    # Relative path resolution
    resolved = resolve_cold_storage_path("bronze/raw_prices/test.parquet", base_dir=base_dir)
    assert resolved == target_file

    # Legacy Windows absolute path resolution on POSIX or vice-versa
    legacy_win_path = r"D:\CPI PIPELINE\data\cold_storage\bronze\raw_prices\test.parquet"
    resolved_legacy = resolve_cold_storage_path(legacy_win_path, base_dir=base_dir)
    assert resolved_legacy == target_file
