"""
tests/test_db_resilience.py
───────────────────────────
Unit tests for database connection pooling, lifecycle management,
and transaction retry with exponential backoff and jitter.
"""

from unittest.mock import MagicMock, call, patch
import psycopg2
import psycopg2.errors
import pytest

from pipeline.config import db_connection, db_cursor, get_db_connection
from pipeline.db_pool import (
    ConnectionPoolManager,
    PooledConnection,
    close_db_pool,
    get_pooled_connection,
)
from pipeline.retry import (
    calculate_backoff_delay,
    retry_db_transaction,
)


@pytest.fixture(autouse=True)
def clean_pool():
    close_db_pool()
    yield
    close_db_pool()


class TestBackoffDelayCalculation:
    def test_backoff_increases_exponentially_without_jitter(self):
        d0 = calculate_backoff_delay(attempt=0, initial_delay=0.1, backoff_factor=2.0, jitter=False)
        d1 = calculate_backoff_delay(attempt=1, initial_delay=0.1, backoff_factor=2.0, jitter=False)
        d2 = calculate_backoff_delay(attempt=2, initial_delay=0.1, backoff_factor=2.0, jitter=False)

        assert d0 == 0.1
        assert d1 == 0.2
        assert d2 == 0.4

    def test_backoff_caps_at_max_delay(self):
        d = calculate_backoff_delay(attempt=10, initial_delay=1.0, max_delay=5.0, jitter=False)
        assert d == 5.0

    def test_backoff_with_jitter_stays_within_bounds(self):
        for attempt in range(5):
            delay = calculate_backoff_delay(
                attempt=attempt, initial_delay=0.1, max_delay=3.0, backoff_factor=2.0, jitter=True
            )
            max_bound = min(3.0, 0.1 * (2.0 ** attempt))
            assert 0.0 <= delay <= max_bound


class TestRetryDecorator:
    def test_succeeds_without_retries_on_clean_run(self):
        mock_fn = MagicMock(return_value="success")
        decorated = retry_db_transaction(max_retries=3)(mock_fn)

        result = decorated("arg1", key="val")
        assert result == "success"
        assert mock_fn.call_count == 1

    @patch("time.sleep", return_value=None)
    def test_retries_and_recovers_from_deadlock(self, mock_sleep):
        mock_conn = MagicMock()
        mock_fn = MagicMock(
            side_effect=[
                psycopg2.errors.DeadlockDetected("deadlock detected"),
                "recovered_result",
            ]
        )
        decorated = retry_db_transaction(max_retries=3, initial_delay=0.01)(mock_fn)

        result = decorated(mock_conn)
        assert result == "recovered_result"
        assert mock_fn.call_count == 2
        # Verify rollback was called on retry to reset transaction state
        mock_conn.rollback.assert_called_once()
        mock_sleep.assert_called_once()

    @patch("time.sleep", return_value=None)
    def test_retries_and_recovers_from_operational_error(self, mock_sleep):
        mock_fn = MagicMock(
            side_effect=[
                psycopg2.OperationalError("server closed the connection unexpectedly"),
                psycopg2.OperationalError("server closed the connection unexpectedly"),
                42,
            ]
        )
        decorated = retry_db_transaction(max_retries=3, initial_delay=0.01)(mock_fn)

        result = decorated()
        assert result == 42
        assert mock_fn.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep", return_value=None)
    def test_raises_after_exceeding_max_retries(self, mock_sleep):
        mock_fn = MagicMock(
            side_effect=psycopg2.errors.DeadlockDetected("persistent deadlock")
        )
        decorated = retry_db_transaction(max_retries=2, initial_delay=0.01)(mock_fn)

        with pytest.raises(psycopg2.errors.DeadlockDetected, match="persistent deadlock"):
            decorated()

        assert mock_fn.call_count == 3  # Initial attempt + 2 retries
        assert mock_sleep.call_count == 2

    def test_does_not_retry_non_transient_exceptions(self):
        mock_fn = MagicMock(side_effect=ValueError("Invalid parameter value"))
        decorated = retry_db_transaction(max_retries=3)(mock_fn)

        with pytest.raises(ValueError, match="Invalid parameter value"):
            decorated()

        assert mock_fn.call_count == 1  # Fails fast immediately


class TestConnectionPool:
    def test_pooled_connection_close_returns_to_pool(self):
        mock_pool = MagicMock()
        mock_raw_conn = MagicMock()
        mock_raw_conn.closed = 0

        pooled = PooledConnection(pool=mock_pool, conn=mock_raw_conn, dsn="mock://dsn")
        assert pooled.raw_connection is mock_raw_conn

        # Closing pooled connection must NOT close physical socket
        pooled.close()
        mock_raw_conn.close.assert_not_called()
        mock_raw_conn.rollback.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)

        # Subsequent close is idempotent
        pooled.close()
        assert mock_pool.putconn.call_count == 1

    def test_pooled_connection_context_manager_commits_and_releases(self):
        mock_pool = MagicMock()
        mock_raw_conn = MagicMock()
        mock_raw_conn.closed = 0

        pooled = PooledConnection(pool=mock_pool, conn=mock_raw_conn, dsn="mock://dsn")
        with pooled as conn:
            assert conn is pooled

        mock_raw_conn.commit.assert_called_once()
        mock_raw_conn.rollback.assert_called_once()  # Called during close cleanup
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)

    def test_pooled_connection_context_manager_rolls_back_on_error(self):
        mock_pool = MagicMock()
        mock_raw_conn = MagicMock()
        mock_raw_conn.closed = 0

        pooled = PooledConnection(pool=mock_pool, conn=mock_raw_conn, dsn="mock://dsn")
        with pytest.raises(RuntimeError, match="simulated failure"):
            with pooled:
                raise RuntimeError("simulated failure")

        mock_raw_conn.commit.assert_not_called()
        mock_raw_conn.rollback.assert_called()
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)

    @patch("pipeline.db_pool.ThreadedConnectionPool")
    def test_manager_discards_dead_connection_on_pre_ping(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool

        dead_conn = MagicMock()
        dead_conn.closed = 1

        live_conn = MagicMock()
        live_conn.closed = 0
        cursor_mock = MagicMock()
        live_conn.cursor.return_value.__enter__.return_value = cursor_mock

        mock_pool.getconn.side_effect = [dead_conn, live_conn]

        manager = ConnectionPoolManager()
        pooled = manager.get_connection("mock://dsn")

        assert pooled.raw_connection is live_conn
        mock_pool.putconn.assert_called_once_with(dead_conn, close=True)

    @patch("pipeline.db_pool.ThreadedConnectionPool")
    def test_db_connection_context_manager(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool

        mock_raw_conn = MagicMock()
        mock_raw_conn.closed = 0
        cursor_mock = MagicMock()
        mock_raw_conn.cursor.return_value.__enter__.return_value = cursor_mock
        mock_pool.getconn.return_value = mock_raw_conn

        with patch("pipeline.config.get_database_url", return_value="mock://cpi_dsn"):
            with db_connection() as conn:
                assert conn.raw_connection is mock_raw_conn

        mock_pool.putconn.assert_called_once_with(mock_raw_conn)

    @patch("pipeline.db_pool.ThreadedConnectionPool")
    def test_db_cursor_context_manager(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool

        mock_raw_conn = MagicMock()
        mock_raw_conn.closed = 0
        mock_cursor = MagicMock()
        mock_raw_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_raw_conn

        with patch("pipeline.config.get_database_url", return_value="mock://cpi_dsn"):
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT * FROM test_table")

        assert call("SELECT * FROM test_table") in mock_cursor.execute.call_args_list
        mock_raw_conn.commit.assert_called()
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)
