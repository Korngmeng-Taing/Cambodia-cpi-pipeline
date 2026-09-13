"""
tests/test_metabase_curator.py
──────────────────────────────
Unit tests for pipeline.metabase_curator.
"""

from unittest.mock import MagicMock, patch
import pytest

from pipeline.metabase_curator import (
    INTERNAL_TABLES,
    curate_metabase_catalog,
    get_metabase_connection,
)


def test_internal_tables_list_integrity():
    """Ensure INTERNAL_TABLES is non-empty and contains valid (schema, table) tuples."""
    assert len(INTERNAL_TABLES) > 0
    for entry in INTERNAL_TABLES:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        schema, table = entry
        assert isinstance(schema, str) and schema.strip()
        assert isinstance(table, str) and table.strip()


@patch("pipeline.metabase_curator.psycopg2.connect")
def test_get_metabase_connection_success(mock_connect):
    """Verify that get_metabase_connection returns connection on valid host."""
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    conn = get_metabase_connection()
    assert conn == mock_conn
    assert mock_connect.called


@patch("pipeline.metabase_curator.psycopg2.connect", side_effect=Exception("Connection refused"))
def test_get_metabase_connection_failure(mock_connect):
    """Verify that get_metabase_connection raises RuntimeError if all hosts fail."""
    with pytest.raises(RuntimeError, match="Could not connect to Metabase database"):
        get_metabase_connection()


@patch("pipeline.metabase_curator.get_metabase_connection")
def test_curate_metabase_catalog_success(mock_get_conn):
    """Verify that curate_metabase_catalog hides partitions and internal tables properly."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_get_conn.return_value = mock_conn

    # Mock execute results:
    # 1st execute: UPDATE partition tables -> rowcount = 57
    # Subsequent executes: UPDATE internal tables -> rowcount = 1 each
    # Final execute: SELECT visible tables -> list of 23 tables
    mock_cur.rowcount = 57
    mock_cur.fetchall.return_value = [
        {"schema": "gold", "name": "fct_daily_cpi"},
        {"schema": "gold", "name": "fct_daily_prices"},
        {"schema": "gold", "name": "dim_items"},
    ]

    res = curate_metabase_catalog(db_id=2)

    assert res["partitions_hidden"] == 57
    assert res["internal_hidden"] >= len(INTERNAL_TABLES)
    assert res["visible_tables_count"] == 3
    assert "gold.fct_daily_cpi" in res["visible_tables"]
    assert mock_conn.commit.called
    assert mock_conn.close.called


@patch("pipeline.metabase_curator.get_metabase_connection")
def test_curate_metabase_catalog_handles_exception(mock_get_conn):
    """Verify that connection is closed even if an exception occurs during curation."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.execute.side_effect = Exception("Database error")
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_get_conn.return_value = mock_conn

    with pytest.raises(Exception, match="Database error"):
        curate_metabase_catalog(db_id=2)

    assert mock_conn.close.called
