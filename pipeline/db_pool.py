"""
pipeline/db_pool.py
───────────────────
Thread-safe PostgreSQL connection pooling with pre-ping validation,
automatic lifecycle management, and transparent failover for the
Cambodia CPI Pipeline.
"""

from __future__ import annotations

import atexit
from contextlib import contextmanager
import logging
import os
import threading
from typing import Any, Iterator
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg2
from psycopg2.pool import PoolError, ThreadedConnectionPool

log = logging.getLogger("pipeline.db_pool")

# Default pool settings (tunable via environment variables)
DEFAULT_MIN_CONN = int(os.getenv("CPI_DB_POOL_MIN", "1"))
DEFAULT_MAX_CONN = int(os.getenv("CPI_DB_POOL_MAX", "20"))


def _alternate_host_url(url: str) -> str:
    """Returns the complementary host DSN (localhost <-> postgres)."""
    parts = urlsplit(url)
    hostname = parts.hostname or "localhost"
    alt_host = "postgres" if hostname == "localhost" else "localhost"
    netloc_parts = []
    if parts.username is not None:
        netloc_parts.append(quote(parts.username, safe=""))
        if parts.password is not None:
            netloc_parts.append(f":{quote(parts.password, safe='')}")
        netloc_parts.append("@")
    netloc_parts.append(alt_host)
    if parts.port:
        netloc_parts.append(f":{parts.port}")
    return urlunsplit(
        (parts.scheme, "".join(netloc_parts), parts.path, parts.query, parts.fragment)
    )


class PooledConnection:
    """
    Transparent proxy around a psycopg2 connection checked out from a
    ThreadedConnectionPool.

    Calling ``conn.close()`` returns the connection to the pool rather than
    terminating the underlying TCP socket. Also supports usage as a context
    manager (commits on clean exit, rolls back on exception, returns to pool).
    """

    def __init__(self, pool: ThreadedConnectionPool, conn: Any, dsn: str):
        self._pool = pool
        self._conn = conn
        self._dsn = dsn
        self._closed = False

    @property
    def raw_connection(self) -> Any:
        """Returns the underlying raw psycopg2 connection."""
        return self._conn

    def close(self) -> None:
        """Returns the underlying connection back to the pool."""
        if not self._closed:
            self._closed = True
            try:
                # Reset any uncommitted transaction before returning to pool
                if not self._conn.closed:
                    self._conn.rollback()
            except Exception as e:
                log.debug("Rollback on pool return encountered error: %s", e)
            try:
                self._pool.putconn(self._conn)
            except Exception as e:
                log.warning("Failed to return connection to pool: %s", e)
                try:
                    self._conn.close()
                except Exception:
                    pass

    def __enter__(self) -> PooledConnection:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
            else:
                try:
                    self._conn.commit()
                except Exception:
                    pass
        finally:
            self.close()

    def __getattr__(self, name: str) -> Any:
        if self._closed:
            raise psycopg2.InterfaceError("Connection is closed (returned to pool).")
        return getattr(self._conn, name)

    def __repr__(self) -> str:
        state = "closed" if self._closed else "active"
        return f"<PooledConnection ({state}) {self._conn!r}>"


class ConnectionPoolManager:
    """
    Manages singleton ThreadedConnectionPool instances by DSN.
    """

    def __init__(self):
        self._pools: dict[str, ThreadedConnectionPool] = {}
        self._lock = threading.Lock()

    def get_pool(
        self,
        dsn: str,
        minconn: int = DEFAULT_MIN_CONN,
        maxconn: int = DEFAULT_MAX_CONN,
    ) -> ThreadedConnectionPool:
        """Gets or initializes a thread-safe connection pool for the given DSN."""
        with self._lock:
            if dsn in self._pools:
                return self._pools[dsn]

            # Try primary DSN, fall back to alternate host if connection fails
            try:
                pool = ThreadedConnectionPool(minconn, maxconn, dsn, connect_timeout=3)
            except psycopg2.OperationalError as primary_err:
                alt_dsn = _alternate_host_url(dsn)
                log.info(
                    "Primary pool connect failed (%s). Attempting alternate host (%s)...",
                    primary_err,
                    alt_dsn,
                )
                try:
                    pool = ThreadedConnectionPool(minconn, maxconn, alt_dsn, connect_timeout=3)
                    dsn = alt_dsn
                except psycopg2.OperationalError:
                    raise primary_err

            self._pools[dsn] = pool
            log.info(
                "Initialized PostgreSQL ThreadedConnectionPool (min=%d, max=%d)",
                minconn,
                maxconn,
            )
            return pool

    def get_connection(
        self,
        dsn: str,
        minconn: int = DEFAULT_MIN_CONN,
        maxconn: int = DEFAULT_MAX_CONN,
    ) -> PooledConnection:
        """
        Borrows a connection from the pool, validating liveness (pre-ping).
        If the connection was terminated, discards it and gets a fresh one.
        """
        pool = self.get_pool(dsn, minconn=minconn, maxconn=maxconn)

        for attempt in range(3):
            try:
                conn = pool.getconn()
            except PoolError as exc:
                log.error("PostgreSQL connection pool exhausted: %s", exc)
                raise

            # Pre-ping liveness validation
            is_alive = False
            try:
                if conn.closed == 0:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                    is_alive = True
            except Exception as ping_err:
                log.debug("Pre-ping liveness failed on pooled connection: %s", ping_err)
                is_alive = False

            if is_alive:
                return PooledConnection(pool=pool, conn=conn, dsn=dsn)

            # Broken connection: discard from pool and try once more
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass

        # Final attempt: fresh connect
        conn = pool.getconn()
        return PooledConnection(pool=pool, conn=conn, dsn=dsn)

    def close_all(self) -> None:
        """Closes all connection pools and their underlying sockets."""
        with self._lock:
            for dsn, pool in list(self._pools.items()):
                try:
                    pool.closeall()
                except Exception as e:
                    log.debug("Error closing connection pool: %s", e)
            self._pools.clear()


# Global pool manager instance
_GLOBAL_POOL_MANAGER = ConnectionPoolManager()


def get_pooled_connection(
    dsn: str,
    minconn: int = DEFAULT_MIN_CONN,
    maxconn: int = DEFAULT_MAX_CONN,
) -> PooledConnection:
    """Acquires a pooled connection managed by the global connection pool."""
    return _GLOBAL_POOL_MANAGER.get_connection(dsn=dsn, minconn=minconn, maxconn=maxconn)


def close_db_pool() -> None:
    """Closes all connections in the global connection pool."""
    _GLOBAL_POOL_MANAGER.close_all()


# Register cleanup at process termination
atexit.register(close_db_pool)


@contextmanager
def db_connection(dsn: str) -> Iterator[PooledConnection]:
    """
    Context manager for database operations using a pooled connection.
    Automatically commits on clean exit, rolls back on exception,
    and returns connection to pool.
    """
    conn = get_pooled_connection(dsn=dsn)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def db_cursor(dsn: str, commit: bool = True) -> Iterator[Any]:
    """
    Context manager providing a database cursor directly from a pooled connection.
    Commits upon block exit if commit=True.
    """
    with db_connection(dsn=dsn) as conn:
        with conn.cursor() as cur:
            yield cur
        if commit:
            conn.commit()
