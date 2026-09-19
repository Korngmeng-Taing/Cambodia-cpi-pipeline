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
import threading
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from pipeline.text_clean import extract_hedonic_specs

try:
    import statsmodels.api as sm
except ImportError:  # pragma: no cover
    sm = None


class _AnalyticalOLSResults:
    """Lightweight analytical OLS results compatible with statsmodels interface."""

    def __init__(self, params: dict[str, float], rsquared: float, nobs: int, fittedvalues: pd.Series, feature_cols: list[str]):
        self.params = params
        self.rsquared = rsquared
        self.nobs = nobs
        self.fittedvalues = fittedvalues
        self._feature_cols = feature_cols

    def predict(self, exog: pd.DataFrame | np.ndarray) -> np.ndarray:
        if isinstance(exog, pd.DataFrame):
            pred = np.full(len(exog), self.params.get("const", 0.0), dtype=float)
            for col in self._feature_cols:
                if col in exog.columns:
                    pred += exog[col].astype(float).values * self.params.get(col, 0.0)
            return pred
        exog_arr = np.asarray(exog, dtype=float)
        # Assume const is first column if exog has 1 + len(feature_cols) cols
        if exog_arr.shape[1] == len(self._feature_cols) + 1:
            coeffs = [self.params.get("const", 0.0)] + [self.params.get(c, 0.0) for c in self._feature_cols]
            return np.dot(exog_arr, coeffs)
        coeffs = [self.params.get(c, 0.0) for c in self._feature_cols]
        return np.dot(exog_arr, coeffs)

log = logging.getLogger(__name__)

COICOP_ELECTRONICS_PREFIX = "09"
HISTORY_MONTHS = 3
MIN_SAMPLE_SIZE = 20  # refuse to fit a model on a tiny sample

# Standard benchmark priors for electronics baseline (used during cold-start or sparse periods)
DEFAULT_BENCHMARK_SPECS: dict[str, float] = {
    "RAM_GB": 8.0,
    "Storage_GB": 128.0,
    "Screen_Inches": 6.5,
    "Camera_MP": 50.0,
    "Is_5G": 1.0,
}



_engine_cache = None
_engine_lock = threading.Lock()

def get_engine():
    global _engine_cache
    with _engine_lock:
        if _engine_cache is not None:
            return _engine_cache
        from pipeline.config import alternate_host_url, get_database_url

        conn_str = get_database_url().replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
        try:
            eng = create_engine(conn_str)
            with eng.connect():
                pass
            _engine_cache = eng
            return eng
        except Exception:
            eng = create_engine(alternate_host_url(conn_str))
            _engine_cache = eng
            return eng


# Extract hedonic characteristics from product name via consolidated text_clean module
extract_specs = extract_hedonic_specs


HEDONIC_FEATURES = ["RAM_GB", "Storage_GB", "Screen_Inches", "Camera_MP", "Is_5G"]


def fetch_hedonic_items(
    engine,
    scrape_date: str | None = None,
    coicop_prefix: str = COICOP_ELECTRONICS_PREFIX,
) -> pd.DataFrame:
    """Returns 08/09* mapped items from the trailing HISTORY_MONTHS months up to scrape_date."""
    as_of = pd.to_datetime(scrape_date).date() if scrape_date else date.today()
    cutoff = (as_of - timedelta(days=30 * HISTORY_MONTHS)).isoformat()
    as_of_str = as_of.isoformat()
    query = text(
        """
        SELECT f.scrape_date, f.item_id::text AS item_id, f.store_slug,
               f.name_clean AS canonical_name, f.price_khr AS raw_price,
               f.coicop_division AS coicop_code
        FROM silver.clean_store_prices f
        WHERE (f.coicop_division = '08' OR f.coicop_division = '09' OR f.coicop_division LIKE :prefix)
          AND f.price_khr > 0
          AND f.scrape_date >= CAST(:cutoff AS DATE)
          AND f.scrape_date <= CAST(:as_of AS DATE)
        """
    )
    with engine.connect() as conn:
        try:
            df = pd.read_sql(
                query,
                conn,
                params={
                    "prefix": f"{coicop_prefix}%",
                    "cutoff": cutoff,
                    "as_of": as_of_str,
                },
            )
        except Exception:
            try:
                # Fallback to int_prices_cleaned in silver if clean_store_prices table is building
                fallback_query = text(
                    """
                    SELECT f.scrape_date, f.item_id::text AS item_id, f.store_slug,
                           f.name_clean AS canonical_name, f.price_khr AS raw_price,
                           coalesce(c.coicop_division, '08') AS coicop_code
                    FROM silver.int_prices_cleaned f
                    LEFT JOIN silver.clean_store_prices c ON c.raw_price_id = f.raw_price_id
                    WHERE f.price_khr > 0
                      AND f.scrape_date >= CAST(:cutoff AS DATE)
                      AND f.scrape_date <= CAST(:as_of AS DATE)
                    """
                )
                df = pd.read_sql(
                    fallback_query,
                    conn,
                    params={"cutoff": cutoff, "as_of": as_of_str},
                )
            except Exception:
                df = pd.DataFrame()
    if df.empty:
        return df

    specs = df["canonical_name"].apply(extract_specs)
    for feat in HEDONIC_FEATURES:
        df[feat] = [s[feat] for s in specs]
    return df


def fit_ols(df: pd.DataFrame) -> dict[str, Any]:
    """
    Fits log-linear model ``ln(raw_price) ~ RAM_GB + Storage_GB + Screen_Inches + Camera_MP + Is_5G`` via OLS.
    Uses statsmodels if available, falling back cleanly to NumPy lstsq.
    Dynamically prunes non-varying features to avoid collinearity and rank-deficiency.
    """
    train = df.dropna(subset=["raw_price"]).copy()
    train = train[train["raw_price"] > 0]
    if len(train) < MIN_SAMPLE_SIZE:
        raise ValueError(
            f"Hedonic model needs >= {MIN_SAMPLE_SIZE} positive-price rows; got {len(train)}"
        )

    # Include features that have non-zero variance (at least 2 distinct values).
    active_features = []
    for feat in HEDONIC_FEATURES:
        if feat in train.columns and train[feat].nunique() > 1:
            active_features.append(feat)
    if not active_features:
        log.warning(
            "Hedonic feature matrix is rank-deficient: no features have variance "
            "(all items share identical specs). Aborting hedonic fit gracefully."
        )
        return {
            "model": None,
            "features": [],
            "params": {},
            "r2": 0.0,
            "n": 0,
            "fitted": pd.Series(dtype=float),
            "specs": pd.DataFrame(),
        }

    X_raw = train[active_features].astype(float)
    if sm is not None:
        X = sm.add_constant(X_raw, has_constant="add")
    else:
        X = np.column_stack([np.ones(len(X_raw)), X_raw.values])
    
    # Rank-deficiency guard: fall back to core features if expanded set is rank-deficient
    if np.linalg.matrix_rank(X) < X.shape[1]:
        active_features = [f for f in ["RAM_GB", "Storage_GB"]
                           if f in train.columns and train[f].nunique() > 1]
        if not active_features:
            log.warning(
                "Hedonic regression aborted: all fallback features have zero "
                "variance (identical specs). Returning 0 adjusted items."
            )
            return {"model": None, "features": [], "params": {}, "r2": 0.0, "n": 0,
                    "fitted": pd.Series(dtype=float), "specs": pd.DataFrame()}
        X_raw = train[active_features].astype(float)
        if sm is not None:
            X = sm.add_constant(X_raw, has_constant="add")
        else:
            X = np.column_stack([np.ones(len(X_raw)), X_raw.values])
        if np.linalg.matrix_rank(X) < X.shape[1]:
            log.warning("Hedonic feature matrix X is rank-deficient even with core features. Aborting.")
            return {"model": None, "features": [], "params": {}, "r2": 0.0, "n": 0,
                    "fitted": pd.Series(dtype=float), "specs": pd.DataFrame()}

    y_log = np.log(train["raw_price"].astype(float))

    if sm is not None:
        model = sm.OLS(y_log, X).fit()
        params_dict = model.params.to_dict()
        r_squared = float(model.rsquared)
        n_obs = int(model.nobs)
        fitted_vals = model.fittedvalues
    else:
        # Analytical Ordinary Least Squares fallback: (X^T X)^-1 X^T y via lstsq
        coeffs, _, _, _ = np.linalg.lstsq(X, y_log.values, rcond=None)
        params_dict = {"const": float(coeffs[0])}
        for i, feat in enumerate(active_features):
            params_dict[feat] = float(coeffs[i + 1])
        y_pred = np.dot(X, coeffs)
        ss_res = np.sum((y_log.values - y_pred) ** 2)
        ss_tot = np.sum((y_log.values - np.mean(y_log.values)) ** 2)
        r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
        n_obs = len(y_log)
        fitted_vals = pd.Series(y_pred, index=train.index)
        model = _AnalyticalOLSResults(params_dict, r_squared, n_obs, fitted_vals, active_features)

    log.info(
        "Hedonic Log-Linear OLS fit: n=%d R2=%.4f features=%s const=%.4f",
        n_obs,
        r_squared,
        active_features,
        params_dict.get("const", 0.0),
    )
    return {
        "model": model,
        "features": active_features,
        "params": params_dict,
        "r2": r_squared,
        "n": n_obs,
        "fitted": fitted_vals,
        "specs": train[active_features],
    }


def baseline_specs(df: pd.DataFrame, current_scrape_date: str) -> dict[str, float]:
    """Average characteristics of items from the previous calendar month (the baseline).

    When no prior-month data exists (e.g. the very first month of collection),
    falls back to the current month's median if available, or to 0.0 / benchmark priors.
    """
    current_month = pd.to_datetime(current_scrape_date).to_period("M")
    prior = df[pd.to_datetime(df["scrape_date"]).dt.to_period("M") < current_month]
    current = df[pd.to_datetime(df["scrape_date"]).dt.to_period("M") == current_month]
    base = {}
    for feat in HEDONIC_FEATURES:
        if not prior.empty and feat in prior.columns:
            base[feat] = float(prior[feat].mean())
        elif not current.empty and feat in current.columns:
            # Fallback: use current month median for neutral adjustment
            base[feat] = float(current[feat].median())
            log.warning(
                "No prior-month data for feature '%s'; using current month median (%.2f) as baseline.",
                feat, base[feat],
            )
        else:
            base[feat] = 0.0
    return base


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
    features = fit.get("features", ["RAM_GB", "Storage_GB"])
    if sm is not None:
        X = sm.add_constant(df[features].astype(float), has_constant="add")
        base_frame = pd.DataFrame([{f: base.get(f, 0.0) for f in features}] * len(df), columns=features)
        base_X = sm.add_constant(base_frame, has_constant="add")
    else:
        X = df[features].astype(float)
        base_frame = pd.DataFrame([{f: base.get(f, 0.0) for f in features}] * len(df), columns=features)
        base_X = base_frame

    log_pred_item = np.asarray(model.predict(X), dtype=float)
    log_pred_base = np.asarray(model.predict(base_X), dtype=float)

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
             raw_price_khr, ram_gb, storage_gb, screen_inches, camera_mp, is_5g,
             hedonic_adjusted_price_khr, adjustment_ratio, model_r2, created_at)
        VALUES
            (:scrape_date, :item_id, :store_slug, :canonical_name, :coicop_division,
             :raw_price_khr, :ram_gb, :storage_gb, :screen_inches, :camera_mp, :is_5g,
             :hedonic_adjusted_price_khr, :adjustment_ratio, :model_r2, CURRENT_TIMESTAMP)
        ON CONFLICT (scrape_date, item_id, store_slug) DO UPDATE
        SET raw_price_khr = EXCLUDED.raw_price_khr,
            ram_gb = EXCLUDED.ram_gb,
            storage_gb = EXCLUDED.storage_gb,
            screen_inches = EXCLUDED.screen_inches,
            camera_mp = EXCLUDED.camera_mp,
            is_5g = EXCLUDED.is_5g,
            hedonic_adjusted_price_khr = EXCLUDED.hedonic_adjusted_price_khr,
            adjustment_ratio = EXCLUDED.adjustment_ratio,
            model_r2 = EXCLUDED.model_r2,
            created_at = CURRENT_TIMESTAMP
        """
    )

    records_dict: dict[tuple[str, str, str], dict[str, Any]] = {}
    for idx, row in current.iterrows():
        adj_price = float(adjusted.loc[idx])
        raw_price = float(row["raw_price"])
        ratio = round(adj_price / raw_price, 4) if raw_price > 0 else 1.0
        div = str(row.get("coicop_code") or row.get("coicop_division") or "08")
        
        def _safe_int(val, default=0):
            try:
                return 0 if pd.isna(val) else int(val)
            except (ValueError, TypeError):
                return default

        def _safe_float(val, default=0.0):
            try:
                return 0.0 if pd.isna(val) else float(val)
            except (ValueError, TypeError):
                return default

        item_id_str = str(row["item_id"])
        store_slug_str = str(row["store_slug"])
        key = (scrape_date, item_id_str, store_slug_str)

        records_dict[key] = {
            "scrape_date": scrape_date,
            "item_id": item_id_str,
            "store_slug": store_slug_str,
            "canonical_name": str(row["canonical_name"]),
            "coicop_division": div,
            "raw_price_khr": raw_price,
            "ram_gb": _safe_int(row.get("RAM_GB", 0)),
            "storage_gb": _safe_int(row.get("Storage_GB", 0)),
            "screen_inches": _safe_float(row.get("Screen_Inches", 0.0)),
            "camera_mp": _safe_int(row.get("Camera_MP", 0)),
            "is_5g": _safe_int(row.get("Is_5G", 0)),
            "hedonic_adjusted_price_khr": adj_price,
            "adjustment_ratio": ratio,
            "model_r2": round(float(fit["r2"]), 4),
        }

    records = list(records_dict.values())

    if not records:
        log.info("No records to persist to silver.hedonic_adjusted_prices for %s", scrape_date)
        return 0

    with engine.begin() as conn:
        conn.execute(stmt, records)

    log.info("Persisted %d unique hedonic-adjusted rows to silver.hedonic_adjusted_prices for %s", len(records), scrape_date)
    return len(records)


def run_hedonic_regression(scrape_date: str) -> dict[str, Any]:
    """
    Hedonic regression entry point (Airflow PythonOperator callable).

    Fits the 09* model on the trailing 3 months, adjusts current prices to the
    previous-month baseline, and persists adjusted values into PostgreSQL.
    """
    engine = get_engine()
    df = fetch_hedonic_items(engine, scrape_date=scrape_date)
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
    if fit.get("model") is None:
        log.warning(
            "Hedonic model could not be fitted (rank-deficient or zero-variance specs); skipping adjustment for %s.",
            scrape_date,
        )
        return {
            "scrape_date": scrape_date,
            "status": "SKIPPED_RANK_DEFICIENT",
            "items_adjusted": 0,
        }

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
        "items_adjusted": len(adjusted),
        "persisted_rows": n_persisted,
    }
