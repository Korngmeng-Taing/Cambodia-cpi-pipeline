"""
tests/test_partition_manager.py
─────────────────────────────────
Unit tests for pipeline.partition_manager.
"""

from unittest.mock import MagicMock
from pipeline.partition_manager import ensure_monthly_partitions


def test_ensure_monthly_partitions_stored_procedure_success():
    """Verify that ensure_monthly_partitions calls the stored procedure first."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    res = ensure_monthly_partitions(months_ahead=3, conn=mock_conn)

    assert res["status"] == "success"
    assert res["method"] == "stored_procedure"
    assert res["months_ahead"] == 3
    mock_cur.execute.assert_any_call("CREATE SCHEMA IF NOT EXISTS ops;")
    mock_cur.execute.assert_any_call("CALL ops.maintain_monthly_partitions(%s);", (3,))
    mock_conn.commit.assert_called_once()


def test_ensure_monthly_partitions_fallback():
    """Verify fallback to direct DDL if stored procedure fails."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Stored procedure raises an exception
    def execute_side_effect(sql, *args):
        if "CALL ops.maintain_monthly_partitions" in sql:
            raise RuntimeError("Procedure does not exist")
        return None

    mock_cur.execute.side_effect = execute_side_effect
    mock_cur.fetchall.return_value = [("bronze", "raw_prices_part"), ("silver", "clean_store_prices_part")]

    res = ensure_monthly_partitions(months_ahead=2, conn=mock_conn)

    assert res["status"] == "success"
    assert res["method"] == "direct_ddl_fallback"
    assert res["months_ahead"] == 2
    assert len(res["partitions"]) > 0
    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_called_once()
