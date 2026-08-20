"""
pipeline/config.py
──────────────────
Configuration constants, database connection helpers, and official COICOP
weights for the Cambodia CPI Medallion Pipeline.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg2

DEFAULT_USD_KHR_RATE = float(os.getenv("DEFAULT_USD_KHR_RATE", "4044"))

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


def get_db_connection():
    """
    Returns a PostgreSQL psycopg2 connection to the CPI database.
    Automatically handles container (postgres:5432) and host (localhost:5432) fallbacks.
    """
    conn_str = os.getenv(
        "CPI_DATABASE_URL",
        "postgresql://cpi_user:cpi_pass@localhost:5432/cpi_db",
    )
    conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
    try:
        return psycopg2.connect(conn_str)
    except psycopg2.OperationalError:
        if "localhost" in conn_str:
            alt = conn_str.replace("localhost:5432", "postgres:5432")
        else:
            alt = conn_str.replace("postgres:5432", "localhost:5432")
        return psycopg2.connect(alt)
