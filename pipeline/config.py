"""
pipeline/config.py
──────────────────
Configuration constants, database connection helpers, and official COICOP
weights for the Cambodia CPI Medallion Pipeline.

Credential resolution order (no embedded defaults — see .env.example):
  1. ``CPI_DATABASE_URL``            full DSN, highest priority
  2. ``DB_USER``/``DB_PASS``/...     individual parts (as set by docker-compose)
  3. otherwise raise RuntimeError    fail fast instead of using known creds
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

try:  # Optional convenience: pick up the project .env for local runs.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

import psycopg2

DEFAULT_USD_KHR_RATE = float(os.getenv("DEFAULT_USD_KHR_RATE", "4044"))

# S2 fix: Sanity check the fallback FX rate. The KHR/USD rate has been in the
# 4000-4200 range since 2010. Warn loudly if the env variable looks wrong.
_EXPECTED_KHR_RANGE = (3500.0, 4500.0)
if not (_EXPECTED_KHR_RANGE[0] <= DEFAULT_USD_KHR_RATE <= _EXPECTED_KHR_RANGE[1]):
    import warnings
    warnings.warn(
        f"DEFAULT_USD_KHR_RATE={DEFAULT_USD_KHR_RATE} is outside the expected "
        f"range {_EXPECTED_KHR_RANGE}. All USD→KHR conversions using this fallback "
        "will be systematically wrong. Update DEFAULT_USD_KHR_RATE in .env.",
        RuntimeWarning,
        stacklevel=2,
    )

# Official NIS Cambodia 12 COICOP Divisions and Consumer Basket Weights
COICOP_WEIGHTS: dict[str, dict[str, Any]] = {
    "01": {"name": "Food and non-alcoholic beverages", "weight": 0.44775},
    "02": {"name": "Alcoholic beverages, tobacco and narcotics", "weight": 0.01625},
    "03": {"name": "Clothing and footwear", "weight": 0.03036},
    "04": {
        "name": "Housing, water, electricity, gas and other fuels",
        "weight": 0.17084,
    },
    "05": {
        "name": "Furnishings, household equipment and routine household maintenance",
        "weight": 0.02743,
    },
    "06": {"name": "Health", "weight": 0.05141},
    "07": {"name": "Transport", "weight": 0.12228},
    "08": {"name": "Communication", "weight": 0.01136},
    "09": {"name": "Recreation and culture", "weight": 0.02912},
    "10": {"name": "Education", "weight": 0.01174},
    "11": {"name": "Restaurants and hotels", "weight": 0.05861},
    "12": {"name": "Miscellaneous goods and services", "weight": 0.02285},
}


def get_database_url() -> str:
    """
    Resolve the CPI database DSN (psycopg2 scheme) without any embedded
    credential default. Raises RuntimeError with remediation hints when
    nothing is configured so misconfiguration fails loudly and early.
    """
    url = os.getenv("CPI_DATABASE_URL")
    if url:
        return url.replace("postgresql+psycopg2://", "postgresql://", 1)

    user = os.getenv("DB_USER") or os.getenv("CPI_DB_USER")
    password = os.getenv("DB_PASS") or os.getenv("CPI_DB_PASSWORD")
    if not (user and password):
        raise RuntimeError(
            "Database credentials not configured: set CPI_DATABASE_URL "
            "(or DB_USER + DB_PASS; see .env.example). Embedded default "
            "credentials were removed for security."
        )

    host = os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("DB_NAME") or os.getenv("CPI_DB_NAME", "cpi_db")
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{name}"
    )


def alternate_host_url(url: str) -> str:
    """
    Return the same DSN pointed at the complementary host
    (localhost <-> postgres), used as container/host failover.
    Parses the URL properly instead of fragile substring matching.

    NOTE: urlsplit returns username/password already URL-decoded, so we
    re-encode exactly once via quote — no unquote() step needed.
    BUG-13 FIX: Use quote() instead of quote_plus() because PostgreSQL
    DSNs require percent-encoding (%20) for spaces, not + encoding.
    """
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


def get_db_connection():
    """
    Returns a pooled PostgreSQL connection to the CPI database with pre-ping validation.
    When conn.close() is called, the connection is automatically returned to the pool.
    Automatically handles container (postgres:5432) and host (localhost:5432) fallbacks.
    """
    use_pool = os.getenv("CPI_DB_POOL_ENABLED", "true").lower() in ("true", "1", "yes")
    conn_str = get_database_url()

    if use_pool:
        from pipeline.db_pool import get_pooled_connection
        return get_pooled_connection(conn_str)

    try:
        return psycopg2.connect(conn_str, connect_timeout=2)
    except psycopg2.OperationalError:
        return psycopg2.connect(alternate_host_url(conn_str))


from contextlib import contextmanager
from typing import Iterator


@contextmanager
def db_connection(dsn: str | None = None) -> Iterator[Any]:
    """
    Context manager providing a managed connection from the pool.
    Commits on normal exit, rolls back on error, and returns connection to pool.
    """
    from pipeline.db_pool import db_connection as _pool_db_conn
    target_dsn = dsn or get_database_url()
    with _pool_db_conn(target_dsn) as conn:
        yield conn


@contextmanager
def db_cursor(commit: bool = True, dsn: str | None = None) -> Iterator[Any]:
    """
    Context manager providing a database cursor directly from a pooled connection.
    Commits on normal exit if commit=True.
    """
    from pipeline.db_pool import db_cursor as _pool_db_cursor
    target_dsn = dsn or get_database_url()
    with _pool_db_cursor(target_dsn, commit=commit) as cur:
        yield cur

