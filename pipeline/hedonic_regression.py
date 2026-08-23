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

    4. Return the adjusted prices in the result payload (no persistence yet —
       no downstream consumer exists; wire one up before storing).

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
_COMPOUND_SPEC_RE = re.compile(
    r"\b(\d{1,2})\s*(?:GB)?\s*/\s*(\d{2,4})\s*GB\b", re.IGNORECASE
)
_RAM_RE = re.compile(r"(\d{1,3})\s*GB\s*(?:RAM|memory)", re.IGNORECASE)
_STORAGE_RE = re.compile(r"(\d{1,4})\s*GB\s*(?:storage|rom|ssd)?", re.IGNORECASE)


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
    ram_val = 0
    storage_val = 0

    # 1. Check compound pattern e.g. "8GB/256GB" or "8/128GB"
    compound = _COMPOUND_SPEC_RE.search(name)
    if compound:
        ram_val = int(compound.group(1))
        storage_val = int(compound.group(2))
        return {"RAM_GB": ram_val, "Storage_GB": storage_val}

    # 2. Check explicit RAM
    ram = _RAM_RE.search(name)
    if ram:
        ram_val = int(ram.group(1))

    # 3. Check Storage / ROM / SSD
    storage_explicit = re.search(
        r"(\d{1,4})\s*GB\s*(?:storage|rom|ssd)", name, re.IGNORECASE
    )
    if storage_explicit:
        storage_val = int(storage_explicit.group(1))
    elif not ram_val:
        standalone = re.search(r"\b(\d{2,4})\s*GB\b", name, re.IGNORECASE)
        if standalone:
            val = int(standalone.group(1))
            if val in (16, 32, 64, 128, 256, 512, 1024):
                storage_val = val

    return {"RAM_GB": ram_val, "Storage_GB": storage_val}


def fetch_hedonic_items(
    engine, coicop_prefix: str = COICOP_ELECTRONICS_PREFIX
) -> pd.DataFrame:
    """Returns 08/09* mapped items from the last HISTORY_MONTHS months (training + current)."""
    cutoff = (date.today() - timedelta(days=30 * HISTORY_MONTHS)).isoformat()
    query = text(
        """
        SELECT f.scrape_date, f.item_id AS raw_item_id, f.store_slug AS source_name,
               f.name_clean AS raw_product_name, f.price_khr AS raw_price, f.item_id AS canonical_item_id,
               f.coicop_division AS coicop_code
        FROM silver.fct_daily_prices f
        WHERE (f.coicop_division = '08' OR f.coicop_division = '09' OR f.coicop_division LIKE :prefix)
          AND f.price_khr > 0
          AND f.scrape_date >= :cutoff::DATE
        """
    )
    with engine.connect() as conn:
        try:
            df = pd.read_sql(
                query, conn, params={"prefix": f"{coicop_prefix}%", "cutoff": cutoff}
            )
        except Exception:
            df = pd.DataFrame()
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
        raise ImportError(
            "statsmodels is required for hedonic regression (pip install statsmodels)"
        )

    train = df.dropna(subset=["raw_price"]).copy()
    train = train[train["raw_price"] > 0]
    if len(train) < MIN_SAMPLE_SIZE:
        raise ValueError(
            f"Hedonic model needs >= {MIN_SAMPLE_SIZE} positive-price rows; got {len(train)}"
        )

    X = sm.add_constant(
        train[["RAM_GB", "Storage_GB"]].astype(float), has_constant="add"
    )
    y_log = np.log(train["raw_price"].astype(float))
    model = sm.OLS(y_log, X).fit()

    log.info(
        "Hedonic Log-Linear OLS fit: n=%d R2=%.4f RAM=%.6f Storage=%.6f const=%.4f",
        int(model.nobs),
        model.rsquared,
        model.params.get("RAM_GB", 0),
        model.params.get("Storage_GB", 0),
        model.params.get("const", 0),
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


def persist_hedonic_adjusted(
    engine,
    current: pd.DataFrame,
    adjusted: pd.Series,
    fit: dict[str, Any],
    scrape_date: str,
) -> int:
    """Persists quality-adjusted constant-spec prices into silver.hedonic_adjusted_prices."""
    if current.empty or adjusted.empty:
        return 0

    stmt = text(
        """
        INSERT INTO silver.hedonic_adjusted_prices
            (scrape_date, item_id, store_slug, canonical_name, coicop_division,
             raw_price_khr, ram_gb, storage_gb, hedonic_adjusted_price_khr,
             adjustment_ratio, model_r2, created_at)
        VALUES
            (:scrape_date, :item_id, :store_slug, :canonical_name, :coicop_division,
             :raw_price_khr, :ram_gb, :storage_gb, :hedonic_adjusted_price_khr,
             :adjustment_ratio, :model_r2, CURRENT_TIMESTAMP)
        ON CONFLICT (scrape_date, item_id, store_slug) DO UPDATE
        SET raw_price_khr = EXCLUDED.raw_price_khr,
            ram_gb = EXCLUDED.ram_gb,
            storage_gb = EXCLUDED.storage_gb,
            hedonic_adjusted_price_khr = EXCLUDED.hedonic_adjusted_price_khr,
            adjustment_ratio = EXCLUDED.adjustment_ratio,
            model_r2 = EXCLUDED.model_r2,
            created_at = CURRENT_TIMESTAMP
        """
    )

    records = []
    for idx, row in current.iterrows():
        adj_price = float(adjusted.loc[idx])
        raw_price = float(row["raw_price"])
        ratio = round(adj_price / raw_price, 4) if raw_price > 0 else 1.0
        records.append(
            {
                "scrape_date": scrape_date,
                "item_id": str(row["item_id"]),
                "store_slug": str(row["store_slug"]),
                "canonical_name": str(row["canonical_name"]),
                "coicop_division": "09",
                "raw_price_khr": raw_price,
                "ram_gb": int(row["RAM_GB"]),
                "storage_gb": int(row["Storage_GB"]),
                "hedonic_adjusted_price_khr": adj_price,
                "adjustment_ratio": ratio,
                "model_r2": round(float(fit["r2"]), 4),
            }
        )

    with engine.begin() as conn:
        for rec in records:
            conn.execute(stmt, rec)

    log.info("Persisted %d hedonic-adjusted rows to silver.hedonic_adjusted_prices for %s", len(records), scrape_date)
    return len(records)


def run_hedonic_regression(scrape_date: str) -> dict[str, Any]:
    """
    Hedonic regression entry point (Airflow PythonOperator callable).

    Fits the 09* model on the trailing 3 months, adjusts current prices to the
    previous-month baseline, and persists adjusted values into PostgreSQL.
    """
    engine = get_engine()
    df = fetch_hedonic_items(engine)
    if df.empty:
        log.warning(
            "No COICOP 09 items in history; skipping hedonic regression for %s",
            scrape_date,
        )
        return {
            "scrape_date": scrape_date,
            "status": "SKIPPED_NO_DATA",
            "items_adjusted": 0,
        }

    fit = fit_ols(df)
    base = baseline_specs(df, scrape_date)
    current = df[
        pd.to_datetime(df["scrape_date"]).dt.date == pd.to_datetime(scrape_date).date()
    ]
    if current.empty:
        log.warning("No current-day items (%s) to adjust; skipping.", scrape_date)
        return {
            "scrape_date": scrape_date,
            "status": "SKIPPED_NO_CURRENT",
            "items_adjusted": 0,
        }

    adjusted = compute_hedonic_adjusted(current, fit, base)
    n_persisted = persist_hedonic_adjusted(engine, current, adjusted, fit, scrape_date)

    return {
        "scrape_date": scrape_date,
        "status": "OK",
        "model_r2": round(fit["r2"], 4),
        "model_n": fit["n"],
        "baseline": base,
        "items_adjusted": int(len(adjusted)),
        "persisted_rows": n_persisted,
    }
