"""
pipeline/hedonic_regression.py
──────────────────────────────
Hedonic regression for COICOP division 09 (electronics) to estimate a
quality-adjusted price per item.

Approach:
    1. Extract hedonic characteristics (RAM_GB, Storage_GB) from the raw product
       name via regex.
    2. Fit OLS ``raw_price ~ RAM_GB + Storage_GB`` (statsmodels) over the trailing
       3 months of mapped 09* items.
    3. Compute ``hedonic_adjusted_price`` for each current item as the raw price
       revalued at the *baseline* specification (previous-month average RAM and
       Storage), holding quality constant:

           hedonic_adjusted_price = raw_price * (pred_at_baseline / pred_at_item)

    4. Persist the adjusted price into staging.stg_item_mapping.

The `hedonic_adjusted_price` column feeds the Silver imputation / final price
layer (dbt fct_daily_prices_parquet / fct_daily_prices_imputed).

Requires: statsmodels>=0.14, sqlalchemy, pandas
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

try:
    import statsmodels.api as sm
except ImportError:  # pragma: no cover
    sm = None

log = logging.getLogger(__name__)

COICOP_ELECTRONICS_PREFIX = "09"
HISTORY_MONTHS = 3
MIN_SAMPLE_SIZE = 20  # refuse to fit a model on a tiny sample

# Regexes for hedonic characteristics embedded in product names, e.g.
# "Samsung Galaxy S24 8GB/256GB", "iPhone 15 Pro 128GB".
_RAM_RE = re.compile(r"(\d{1,3})\s*GB\s*(?:RAM|memory)", re.IGNORECASE)
_STORAGE_RE = re.compile(r"(\d{1,3})\s*GB\s*(?:storage|rom|ssd)", re.IGNORECASE)


def get_engine():
    conn_str = os.getenv(
        "CPI_DATABASE_URL",
        "postgresql+psycopg2://cpi_user:cpi_pass@postgres:5432/cpi_db",
    )
    return create_engine(conn_str)


def extract_specs(name: str) -> dict[str, int]:
    """
    Extracts (RAM_GB, Storage_GB) from a raw product name using regex.
    Returns both as 0 when a characteristic is not present (0 = base level).
    """
    name = str(name)
    ram = _RAM_RE.search(name)
    storage = _STORAGE_RE.search(name)
    return {
        "RAM_GB": int(ram.group(1)) if ram else 0,
        "Storage_GB": int(storage.group(1)) if storage else 0,
    }


def fetch_hedonic_items(engine, coicop_prefix: str = COICOP_ELECTRONICS_PREFIX) -> pd.DataFrame:
    """Returns 09* mapped items from the last HISTORY_MONTHS months (training + current)."""
    cutoff = (date.today() - timedelta(days=30 * HISTORY_MONTHS)).isoformat()
    query = text(
        """
        SELECT m.scrape_date, m.raw_item_id, m.source_name,
               m.raw_product_name, f.price_khr AS raw_price, m.canonical_item_id,
               d.coicop_code
        FROM staging.stg_item_mapping m
        JOIN silver.dim_canonical_products d
          ON d.canonical_item_id = m.canonical_item_id
        LEFT JOIN silver.fct_daily_prices f
          ON f.scrape_date = m.scrape_date
         AND f.store_slug = m.source_name
         AND f.item_id = m.canonical_item_id::TEXT
        WHERE d.coicop_code LIKE :prefix
          AND f.price_khr IS NOT NULL
          AND m.scrape_date >= :cutoff::DATE
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"prefix": f"{coicop_prefix}%", "cutoff": cutoff})
    if df.empty:
        return df

    specs = df["raw_product_name"].apply(extract_specs)
    df["RAM_GB"] = [s["RAM_GB"] for s in specs]
    df["Storage_GB"] = [s["Storage_GB"] for s in specs]
    return df


def fit_ols(df: pd.DataFrame) -> dict[str, Any]:
    """
    Fits log-linear model ``ln(raw_price) ~ RAM_GB + Storage_GB`` via statsmodels OLS.
    Standard econometric semi-log specification for quality adjustment.
    """
    if sm is None:
        raise ImportError("statsmodels is required for hedonic regression (pip install statsmodels)")

    train = df.dropna(subset=["raw_price"]).copy()
    train = train[train["raw_price"] > 0]
    if len(train) < MIN_SAMPLE_SIZE:
        raise ValueError(
            f"Hedonic model needs >= {MIN_SAMPLE_SIZE} positive-price rows; got {len(train)}"
        )

    X = sm.add_constant(train[["RAM_GB", "Storage_GB"]].astype(float), has_constant="add")
    y_log = np.log(train["raw_price"].astype(float))
    model = sm.OLS(y_log, X).fit()

    log.info(
        "Hedonic Log-Linear OLS fit: n=%d R2=%.4f RAM=%.6f Storage=%.6f const=%.4f",
        int(model.nobs), model.rsquared, model.params.get("RAM_GB", 0),
        model.params.get("Storage_GB", 0), model.params.get("const", 0),
    )
    return {
        "model": model,
        "params": model.params.to_dict(),
        "r2": float(model.rsquared),
        "n": int(model.nobs),
        "fitted": model.fittedvalues,
        "specs": train[["RAM_GB", "Storage_GB"]],
    }


def baseline_specs(df: pd.DataFrame, current_scrape_date: str) -> dict[str, float]:
    """Average RAM/Storage of items from the previous calendar month (the baseline)."""
    current_month = pd.to_datetime(current_scrape_date).to_period("M")
    prior = df[pd.to_datetime(df["scrape_date"]).dt.to_period("M") < current_month]
    if prior.empty:
        return {"RAM_GB": 0.0, "Storage_GB": 0.0}
    return {
        "RAM_GB": float(prior["RAM_GB"].mean()),
        "Storage_GB": float(prior["Storage_GB"].mean()),
    }


def compute_hedonic_adjusted(
    df: pd.DataFrame,
    fit: dict[str, Any],
    base: dict[str, float],
) -> pd.Series:
    """
    Quality-adjusted price = raw_price * exp(ln_pred_at_baseline - ln_pred_at_item).
    Prices items at the baseline specification, holding quality constant.
    """
    model = fit["model"]
    X = sm.add_constant(df[["RAM_GB", "Storage_GB"]].astype(float), has_constant="add")
    log_pred_item = np.asarray(model.predict(X), dtype=float)
    base_frame = pd.DataFrame([base] * len(df), columns=["RAM_GB", "Storage_GB"])
    log_pred_base = np.asarray(
        model.predict(sm.add_constant(base_frame, has_constant="add")),
        dtype=float,
    )
    # Quality ratio = exp(ln_base - ln_item)
    ratio = np.exp(np.clip(log_pred_base - log_pred_item, -3.0, 3.0))
    adjusted = np.asarray(df["raw_price"].astype(float)) * ratio
    return pd.Series(np.round(adjusted, 2), index=df.index)


def persist_adjusted_prices(engine, scrape_date: str, adjusted: pd.Series, raw_item_ids: pd.Series) -> int:
    """Writes hedonic_adjusted_price back into staging.stg_item_mapping."""
    rows = pd.DataFrame({"rid": raw_item_ids.astype(str), "adj": adjusted})
    rows = rows.dropna(subset=["adj"]).drop_duplicates(subset=["rid"])
    if rows.empty:
        return 0

    updated = 0
    with engine.begin() as conn:
        for _, row in rows.iterrows():
            result = conn.execute(
                text(
                    """
                    UPDATE staging.stg_item_mapping
                    SET hedonic_adjusted_price = :adj
                    WHERE source_name = (SELECT source_name FROM staging.stg_item_mapping
                                         WHERE raw_item_id = :rid LIMIT 1)
                      AND raw_item_id = :rid
                      AND scrape_date = :date
                    """
                ),
                {"adj": float(row["adj"]), "rid": row["rid"], "date": scrape_date},
            )
            updated += result.rowcount or 0
    log.info("Updated hedonic_adjusted_price for %d row(s) on %s", updated, scrape_date)
    return updated


def run_hedonic_regression(scrape_date: str) -> dict[str, Any]:
    """
    Hedonic regression entry point (Airflow PythonOperator callable).

    Fits the 09* model on the trailing 3 months, adjusts current prices to the
    previous-month baseline, and persists hedonic_adjusted_price.
    """
    engine = get_engine()
    df = fetch_hedonic_items(engine)
    if df.empty:
        log.warning("No COICOP 09 items in history; skipping hedonic regression for %s", scrape_date)
        return {"scrape_date": scrape_date, "status": "SKIPPED_NO_DATA", "items_adjusted": 0}

    fit = fit_ols(df)
    base = baseline_specs(df, scrape_date)
    current = df[pd.to_datetime(df["scrape_date"]).dt.date == pd.to_datetime(scrape_date).date()]
    if current.empty:
        log.warning("No current-day items (%s) to adjust; skipping.", scrape_date)
        return {"scrape_date": scrape_date, "status": "SKIPPED_NO_CURRENT", "items_adjusted": 0}

    adjusted = compute_hedonic_adjusted(current, fit, base)
    n_updated = persist_adjusted_prices(engine, scrape_date, adjusted, current["raw_item_id"])

    return {
        "scrape_date": scrape_date,
        "status": "OK",
        "model_r2": round(fit["r2"], 4),
        "model_n": fit["n"],
        "baseline": base,
        "items_adjusted": n_updated,
    }
