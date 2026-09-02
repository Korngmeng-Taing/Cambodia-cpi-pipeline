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
from urllib.parse import quote_plus, urlsplit, urlunsplit

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
    "01": {"name": "Food and non-alcoholic beverages", "weight": 0.44800},
    "02": {"name": "Alcoholic beverages, tobacco and narcotics", "weight": 0.01500},
    "03": {"name": "Clothing and footwear", "weight": 0.02900},
    "04": {
        "name": "Housing, water, electricity, gas and other fuels",
        "weight": 0.17100,
    },
    "05": {
        "name": "Furnishings, household equipment and routine household maintenance",
        "weight": 0.03300,
    },
    "06": {"name": "Health", "weight": 0.05600},
    "07": {"name": "Transport", "weight": 0.12200},
    "08": {"name": "Communication", "weight": 0.03900},
    "09": {"name": "Recreation and culture", "weight": 0.01900},
    "10": {"name": "Education", "weight": 0.01500},
    "11": {"name": "Restaurants and hotels", "weight": 0.03100},
    "12": {"name": "Miscellaneous goods and services", "weight": 0.02200},
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
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}"
    )


def alternate_host_url(url: str) -> str:
    """
    Return the same DSN pointed at the complementary host
    (localhost <-> postgres), used as container/host failover.
    Parses the URL properly instead of fragile substring matching.

    NOTE: urlsplit returns username/password already URL-decoded, so we
    re-encode exactly once via quote_plus — no unquote() step needed.
    """
    parts = urlsplit(url)
    hostname = parts.hostname or "localhost"
    alt_host = "postgres" if hostname == "localhost" else "localhost"
    netloc_parts = []
    if parts.username is not None:
        netloc_parts.append(quote_plus(parts.username))
        if parts.password is not None:
            netloc_parts.append(f":{quote_plus(parts.password)}")
        netloc_parts.append("@")
    netloc_parts.append(alt_host)
    if parts.port:
        netloc_parts.append(f":{parts.port}")
    return urlunsplit(
        (parts.scheme, "".join(netloc_parts), parts.path, parts.query, parts.fragment)
    )


def get_db_connection():
    """
    Returns a PostgreSQL psycopg2 connection to the CPI database.
    Automatically handles container (postgres:5432) and host (localhost:5432) fallbacks.
    """
    conn_str = get_database_url()
    try:
        return psycopg2.connect(conn_str, connect_timeout=2)
    except psycopg2.OperationalError:
        return psycopg2.connect(alternate_host_url(conn_str))
