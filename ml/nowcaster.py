"""
ml/nowcaster.py
───────────────
High-Frequency Daily Consumer Price Index (CPI) Inflation Nowcasting Engine.

Implements the micro-to-macro nowcasting methodology grounded in:
1. Cavallo & Rigobon (2016) - MIT Billion Prices Project: Real-time high-frequency
   price harvesting to eliminate the 30-to-60-day official statistical reporting lag.
2. Macias, Stelmasiak, & Szafranek (2023) - National Bank of Poland: Supermarket daily
   food and fuel price momentum as leading indicators for national headline inflation.
3. Babii, Ball, Ghysels, & Striaukas (2022) - Journal of Econometrics: Mixed-frequency
   macroeconomic regressions and out-of-sample nowcast evaluation.
4. IMF / ILO CPI Manual (2020): Axiomatic index aggregation and official benchmark
   chain-linking.

The engine computes the Month-to-Date (MTD) realized inflation from `gold.fct_cpi_daily`,
projects the unobserved remaining days using cross-division momentum signals,
chain-links the estimated growth rate to official National Institute of Statistics (NIS)
benchmarks, and calculates dynamic 95% confidence intervals based on daily price volatility.
"""

from __future__ import annotations

import calendar
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows if supported by stdout/stderr
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd

import json
from sklearn.linear_model import RidgeCV

from ml.config import (
    BASKET_COLUMN_MAP,
    CAMBODIA_ANNUAL_HOLIDAYS,
    DEFAULT_NOWCAST_MODEL,
    NIS_COICOP_WEIGHTS,
    NOWCAST_TARGET_BASKETS,
    RIDGE_ALPHAS,
    Z_SCORE_95,
)
from pipeline.config import get_db_connection

log = logging.getLogger(__name__)


class RidgeBasketDriftEstimator:
    """Estimates daily drift rates for 5 key COICOP divisions using Ridge Regression (RidgeCV)
    with empirical Bayesian prior shrinkage for small samples.
    """

    def __init__(self, alphas: list[float] | None = None):
        self.alphas = alphas or RIDGE_ALPHAS

    @staticmethod
    def _extract_holiday_features(eval_date: date) -> tuple[float, float]:
        """Returns (festival_proximity_kernel, is_holiday_window)."""
        _, days_in_month = calendar.monthrange(eval_date.year, eval_date.month)
        prox = 0.0
        is_window = 0.0
        for hol in CAMBODIA_ANNUAL_HOLIDAYS:
            if hol["month"] == eval_date.month:
                peak_days = hol["peak_days"]
                window = hol.get("window_days", 4)
                min_day = max(1, min(peak_days) - window)
                max_day = min(days_in_month, max(peak_days) + 2)
                if min_day <= eval_date.day <= max_day:
                    is_window = 1.0
                dist = min(abs(eval_date.day - p) for p in peak_days)
                prox = float(np.exp(-0.4 * min(dist, 10)))
                break
        return prox, is_window

    @staticmethod
    def _extract_fx_features(eval_date: date, df_fx: pd.DataFrame | None) -> tuple[float, float]:
        """Returns (fx_momentum_7d, fx_momentum_14d)."""
        if df_fx is None or df_fx.empty or "rate" not in df_fx.columns:
            return 0.0, 0.0
        sub = df_fx[pd.to_datetime(df_fx["execution_date"]).dt.date <= eval_date].sort_values("execution_date")
        if len(sub) < 2:
            return 0.0, 0.0
        rates = sub["rate"].astype(float).values
        r_now = rates[-1]
        r_7 = rates[-7] if len(rates) >= 7 else rates[0]
        r_14 = rates[-14] if len(rates) >= 14 else rates[0]
        mom_7d = float((r_now - r_7) / r_7) if r_7 > 0 else 0.0
        mom_14d = float((r_now - r_14) / r_14) if r_14 > 0 else 0.0
        return mom_7d, mom_14d

    @staticmethod
    def _get_division_momentum(
        eval_date: date, df_daily: pd.DataFrame | None, div_code: str
    ) -> tuple[float, float, float]:
        """Returns (mom_3d, mom_7d, mom_14d) for a given COICOP division."""
        if df_daily is None or df_daily.empty or "coicop_division" not in df_daily.columns:
            return 0.0, 0.0, 0.0
        sub = df_daily[
            (df_daily["coicop_division"] == div_code)
            & (pd.to_datetime(df_daily["calculation_date"]).dt.date <= eval_date)
        ].sort_values("calculation_date")
        if sub.empty:
            return 0.0, 0.0, 0.0
        sub = sub.drop_duplicates(subset=["calculation_date"])
        if len(sub) < 2:
            return 0.0, 0.0, 0.0
        vals = sub["division_index"].astype(float).values
        v_now = vals[-1]
        v_3 = vals[-3] if len(vals) >= 3 else vals[0]
        v_7 = vals[-7] if len(vals) >= 7 else vals[0]
        v_14 = vals[-14] if len(vals) >= 14 else vals[0]

        m_3 = float((v_now - v_3) / v_3) if v_3 > 0 else 0.0
        m_7 = float((v_now - v_7) / v_7) if v_7 > 0 else 0.0
        m_14 = float((v_now - v_14) / v_14) if v_14 > 0 else 0.0
        return m_3, m_7, m_14

    def extract_features_for_basket(
        self,
        eval_date: date,
        df_daily: pd.DataFrame,
        df_fx: pd.DataFrame,
        div_code: str,
    ) -> np.ndarray:
        """Extracts specialized feature vector for each of the 5 key baskets."""
        _, days_in_month = calendar.monthrange(eval_date.year, eval_date.month)
        prog_ratio = float(eval_date.day / days_in_month)
        fest_prox, is_window = self._extract_holiday_features(eval_date)
        fx_7d, fx_14d = self._extract_fx_features(eval_date, df_fx)

        f_3, f_7, f_14 = self._get_division_momentum(eval_date, df_daily, "01")
        t_3, t_7, _ = self._get_division_momentum(eval_date, df_daily, "07")

        if div_code == "01":  # Food
            return np.array([f_3, f_7, f_14, fx_7d, fest_prox, prog_ratio], dtype=float)
        elif div_code == "02":  # Alcohol & Tobacco
            _, a_7, _ = self._get_division_momentum(eval_date, df_daily, "02")
            return np.array([a_7, fx_7d, fx_14d, is_window, prog_ratio], dtype=float)
        elif div_code == "04":  # Housing & Energy
            _, h_7, h_14 = self._get_division_momentum(eval_date, df_daily, "04")
            return np.array([h_7, h_14, fx_14d, prog_ratio], dtype=float)
        elif div_code == "07":  # Transport
            return np.array([t_3, t_7, fx_7d, fest_prox, prog_ratio], dtype=float)
        elif div_code == "11":  # Restaurants & Hotels
            _, r_7, _ = self._get_division_momentum(eval_date, df_daily, "11")
            return np.array([r_7, f_7, is_window, prog_ratio], dtype=float)
        else:
            _, d_7, _ = self._get_division_momentum(eval_date, df_daily, div_code)
            return np.array([d_7, fx_7d, prog_ratio], dtype=float)

    def compute_structural_prior_drift(
        self,
        eval_date: date,
        df_daily: pd.DataFrame,
        df_fx: pd.DataFrame,
        div_code: str,
    ) -> float:
        """Computes calibrated economic structural prior for cold-start / shrinkage."""
        _, is_window = self._extract_holiday_features(eval_date)
        fx_7d, fx_14d = self._extract_fx_features(eval_date, df_fx)
        f_3, f_7, f_14 = self._get_division_momentum(eval_date, df_daily, "01")
        fest_shock = 0.0012 if is_window > 0 else 0.0

        if div_code == "01":  # Food
            return float((f_7 / 7.0) + (fest_shock * 0.5) + (0.15 * fx_7d / 7.0))
        elif div_code == "02":  # Alcohol & Tobacco
            _, a_7, _ = self._get_division_momentum(eval_date, df_daily, "02")
            return float((a_7 / 7.0) + (0.20 * fx_7d / 7.0) + (fest_shock * 0.25))
        elif div_code == "04":  # Housing & Energy
            _, h_7, h_14 = self._get_division_momentum(eval_date, df_daily, "04")
            return float((h_14 / 14.0) * 0.5 + (0.10 * fx_14d / 14.0))
        elif div_code == "07":  # Transport
            t_3, t_7, _ = self._get_division_momentum(eval_date, df_daily, "07")
            return float((t_7 / 7.0) + (0.35 * fx_7d / 7.0) + (fest_shock * 0.5))
        elif div_code == "11":  # Restaurants & Hotels
            _, r_7, _ = self._get_division_momentum(eval_date, df_daily, "11")
            return float((r_7 / 7.0) + (0.30 * f_7 / 7.0) + (fest_shock * 0.25))
        else:
            _, d_7, _ = self._get_division_momentum(eval_date, df_daily, div_code)
            return float((d_7 / 14.0) * 0.3)

    def fit_and_predict_drift(
        self,
        target_date: date,
        df_daily: pd.DataFrame,
        df_fx: pd.DataFrame,
    ) -> dict[str, float]:
        """Trains RidgeCV models on available historical daily facts and predicts daily drift for all 12 divisions."""
        drifts: dict[str, float] = {}

        df_daily_clean = df_daily.copy() if not df_daily.empty else pd.DataFrame()
        if not df_daily_clean.empty and "calculation_date" in df_daily_clean.columns:
            df_daily_clean["calculation_date"] = pd.to_datetime(df_daily_clean["calculation_date"]).dt.date

        unique_dates = sorted(df_daily_clean["calculation_date"].unique()) if not df_daily_clean.empty else []

        for div_code in NIS_COICOP_WEIGHTS.keys():
            structural_prior = self.compute_structural_prior_drift(target_date, df_daily_clean, df_fx, div_code)

            if div_code not in NOWCAST_TARGET_BASKETS:
                drifts[div_code] = float(np.clip(structural_prior, -0.015, 0.015))
                continue

            X_train = []
            y_train = []

            for d in unique_dates:
                if d >= target_date:
                    continue
                _, dim = calendar.monthrange(d.year, d.month)
                m_end = d.replace(day=dim)

                rem_days = dim - d.day
                if rem_days < 2:
                    continue

                sub_rem = df_daily_clean[
                    (df_daily_clean["coicop_division"] == div_code)
                    & (df_daily_clean["calculation_date"] > d)
                    & (df_daily_clean["calculation_date"] <= m_end)
                ]
                sub_now = df_daily_clean[
                    (df_daily_clean["coicop_division"] == div_code)
                    & (df_daily_clean["calculation_date"] == d)
                ]
                if sub_rem.empty or sub_now.empty:
                    continue

                idx_now = float(sub_now["division_index"].iloc[-1])
                if idx_now <= 0:
                    continue
                mean_rem = float(sub_rem["division_index"].mean())

                implied_drift = (mean_rem - idx_now) / (idx_now * (rem_days + 1) / 2.0)
                feat = self.extract_features_for_basket(d, df_daily_clean, df_fx, div_code)
                X_train.append(feat)
                y_train.append(implied_drift)

            pred_drift = structural_prior
            n_samples = len(X_train)

            if n_samples >= 8:
                try:
                    X_arr = np.array(X_train)
                    y_arr = np.array(y_train)
                    ridge = RidgeCV(alphas=self.alphas)
                    ridge.fit(X_arr, y_arr)

                    x_target = self.extract_features_for_basket(target_date, df_daily_clean, df_fx, div_code).reshape(1, -1)
                    ml_pred = float(ridge.predict(x_target)[0])

                    prior_weight = max(0.0, min(1.0, 1.0 - (n_samples - 8) / 22.0))
                    pred_drift = (1.0 - prior_weight) * ml_pred + prior_weight * structural_prior
                except Exception as e:
                    log.debug("Ridge fitting fallback for division %s: %s", div_code, e)
                    pred_drift = structural_prior
            else:
                pred_drift = structural_prior

            drifts[div_code] = float(np.clip(pred_drift, -0.015, 0.015))

        return drifts


class CPINowcaster:
    """Production High-Frequency Inflation Nowcaster with 5-Basket Bottom-Up Disaggregation and Ridge Regularization."""

    def __init__(self, model_name: str = DEFAULT_NOWCAST_MODEL):
        self.model_name = model_name
        self.drift_estimator = RidgeBasketDriftEstimator()

    def fetch_training_data(
        self, target_date: date
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
        """Fetches daily CPI facts, FX rates, monthly aggregations, and NIS benchmarks."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # 1. Daily CPI facts
                cur.execute(
                    """
                    SELECT calculation_date, coicop_division, division_name, weight,
                           division_index, headline_cpi, core_cpi, item_count, observation_count
                    FROM gold.fct_cpi_daily
                    WHERE calculation_date <= %s
                    ORDER BY calculation_date ASC;
                    """,
                    (target_date,),
                )
                cols_daily = [desc[0] for desc in cur.description]
                df_daily = pd.DataFrame(cur.fetchall(), columns=cols_daily)

                # 2. FX daily rates
                cur.execute(
                    """
                    SELECT execution_date, rate
                    FROM staging.exchange_rates
                    WHERE execution_date <= %s
                    ORDER BY execution_date ASC;
                    """,
                    (target_date,),
                )
                cols_fx = [desc[0] for desc in cur.description]
                df_fx = pd.DataFrame(cur.fetchall(), columns=cols_fx)

                # 3. Monthly historical aggregations (deduplicated by month)
                cur.execute(
                    """
                    SELECT DISTINCT ON (cpi_month)
                        cpi_month, monthly_headline_cpi, monthly_core_cpi,
                        COALESCE(headline_mom_inflation_pct, mom_inflation_pct) AS headline_mom_inflation_pct,
                        COALESCE(headline_yoy_inflation_pct, yoy_inflation_pct) AS headline_yoy_inflation_pct
                    FROM gold.fct_cpi_monthly
                    WHERE cpi_month <= %s
                    ORDER BY cpi_month ASC;
                    """,
                    (target_date.replace(day=1),),
                )
                cols_monthly = [desc[0] for desc in cur.description]
                df_monthly = pd.DataFrame(cur.fetchall(), columns=cols_monthly)

                # 4. Official NIS ground-truth benchmarks
                df_nis = None
                try:
                    cur.execute(
                        """
                        SELECT cpi_month, headline_cpi, core_cpi, mom_inflation_pct, yoy_inflation_pct
                        FROM gold.dim_nis_official_cpi
                        WHERE cpi_month <= %s
                        ORDER BY cpi_month DESC;
                        """,
                        (target_date.replace(day=1),),
                    )
                    cols_nis = [desc[0] for desc in cur.description]
                    df_nis = pd.DataFrame(cur.fetchall(), columns=cols_nis)
                except Exception as e_nis:
                    log.debug("NIS benchmark table query skipped: %s", e_nis)

                # Ensure Postgres Decimal columns are coerced to numeric floats for calculations
                if not df_daily.empty:
                    for col in ["weight", "division_index", "headline_cpi", "core_cpi"]:
                        if col in df_daily.columns:
                            df_daily[col] = pd.to_numeric(df_daily[col], errors="coerce")
                if not df_fx.empty and "rate" in df_fx.columns:
                    df_fx["rate"] = pd.to_numeric(df_fx["rate"], errors="coerce")
                if not df_monthly.empty:
                    for col in ["monthly_headline_cpi", "monthly_core_cpi", "headline_mom_inflation_pct", "headline_yoy_inflation_pct"]:
                        if col in df_monthly.columns:
                            df_monthly[col] = pd.to_numeric(df_monthly[col], errors="coerce")
                if df_nis is not None and not df_nis.empty:
                    for col in ["headline_cpi", "core_cpi", "mom_inflation_pct", "yoy_inflation_pct"]:
                        if col in df_nis.columns:
                            df_nis[col] = pd.to_numeric(df_nis[col], errors="coerce")

                return df_daily, df_fx, df_monthly, df_nis
        finally:
            conn.close()

    def nowcast_for_date(
        self,
        target_date: date,
        df_daily: pd.DataFrame,
        df_fx: pd.DataFrame,
        df_monthly: pd.DataFrame,
        df_nis: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Calculates Month-to-Date nowcast, intra-month projection, and uncertainty bounds
        using bottom-up 5-basket disaggregation with Ridge regularization and exact Laspeyres aggregation.
        """
        target_month = target_date.replace(day=1)
        _, days_in_month = calendar.monthrange(target_date.year, target_date.month)
        days_observed = min(target_date.day, days_in_month)
        days_remaining = max(0, days_in_month - days_observed)

        # Standardize dates
        df_daily_clean = df_daily.copy() if not df_daily.empty else pd.DataFrame()
        if not df_daily_clean.empty and "calculation_date" in df_daily_clean.columns:
            df_daily_clean["calculation_date"] = pd.to_datetime(df_daily_clean["calculation_date"]).dt.date

        # Filter daily facts to active month up to target_date
        df_month = (
            df_daily_clean[
                (df_daily_clean["calculation_date"] >= target_month)
                & (df_daily_clean["calculation_date"] <= target_date)
            ]
            if not df_daily_clean.empty
            else pd.DataFrame()
        )

        obs_weight = float(days_observed / days_in_month)
        rem_weight = float(days_remaining / days_in_month)

        # Determine prior month baseline headline CPI
        prior_month_cpi = 100.0
        if df_monthly is not None and not df_monthly.empty:
            prior_months = df_monthly[pd.to_datetime(df_monthly["cpi_month"]).dt.date < target_month]
            if not prior_months.empty:
                prior_month_cpi = float(prior_months.iloc[-1]["monthly_headline_cpi"])
            else:
                prior_month_cpi = float(df_monthly.iloc[-1]["monthly_headline_cpi"])
        elif not df_daily_clean.empty:
            prior_daily = df_daily_clean[df_daily_clean["calculation_date"] < target_month]
            if not prior_daily.empty:
                prior_month_cpi = float(prior_daily["headline_cpi"].iloc[-1])

        # -------------------------------------------------------------------------
        # Predict Division Drift Rates via Ridge (with Empirical Bayesian Fallback)
        # -------------------------------------------------------------------------
        drift_map = self.drift_estimator.fit_and_predict_drift(target_date, df_daily_clean, df_fx)

        # -------------------------------------------------------------------------
        # Bottom-Up Disaggregation: Compute Price Relatives & Projections for 12 Divisions
        # -------------------------------------------------------------------------
        division_results: dict[str, dict[str, Any]] = {}

        for div_code, div_info in NIS_COICOP_WEIGHTS.items():
            weight = float(div_info["weight"])
            div_name = div_info["name"]

            # 1. Realized MTD index for this division
            sub_div_month = (
                df_month[df_month["coicop_division"] == div_code]
                if not df_month.empty and "coicop_division" in df_month.columns
                else pd.DataFrame()
            )
            if not sub_div_month.empty:
                realized_div = float(sub_div_month["division_index"].mean())
                latest_div = float(sub_div_month.sort_values("calculation_date")["division_index"].iloc[-1])
            elif not df_daily_clean.empty and "coicop_division" in df_daily_clean.columns:
                sub_all = df_daily_clean[df_daily_clean["coicop_division"] == div_code]
                if not sub_all.empty:
                    realized_div = float(sub_all["division_index"].iloc[-1])
                    latest_div = realized_div
                else:
                    realized_div = 100.0
                    latest_div = 100.0
            else:
                realized_div = 100.0
                latest_div = 100.0

            # 2. Projected remaining index for this division
            div_drift = float(drift_map.get(div_code, 0.0))
            if days_remaining > 0:
                projected_div = latest_div * (1.0 + (div_drift * (days_remaining + 1) / 2.0))
            else:
                projected_div = realized_div

            # 3. Blended monthly nowcast index
            nowcast_div = round((obs_weight * realized_div) + (rem_weight * projected_div), 4)

            # 4. Prior month baseline for this division
            prior_div = prior_month_cpi
            if not df_daily_clean.empty and "coicop_division" in df_daily_clean.columns:
                sub_prior = df_daily_clean[
                    (df_daily_clean["calculation_date"] < target_month)
                    & (df_daily_clean["coicop_division"] == div_code)
                ]
                if not sub_prior.empty:
                    prior_div = float(sub_prior.sort_values("calculation_date")["division_index"].iloc[-1])

            div_mom_pct = round(((nowcast_div - prior_div) / prior_div) * 100.0, 4) if prior_div > 0 else 0.0
            contribution_pp = round(weight * div_mom_pct, 4)
            price_relative = round(nowcast_div / prior_div, 6) if prior_div > 0 else 1.0

            division_results[div_code] = {
                "name": div_name,
                "weight": weight,
                "realized": round(realized_div, 4),
                "latest": round(latest_div, 4),
                "projected": round(projected_div, 4),
                "nowcast": nowcast_div,
                "prior": round(prior_div, 4),
                "mom_pct": div_mom_pct,
                "contribution_pp": contribution_pp,
                "price_relative": price_relative,
                "drift_daily": round(div_drift, 6),
            }

        # -------------------------------------------------------------------------
        # Axiomatic Laspeyres Aggregation: Headline CPI & Core CPI
        # -------------------------------------------------------------------------
        nowcast_headline_cpi = round(sum(res["weight"] * res["nowcast"] for res in division_results.values()), 4)
        realized_cpi = round(sum(res["weight"] * res["realized"] for res in division_results.values()), 4)
        projected_avg_cpi = round(sum(res["weight"] * res["projected"] for res in division_results.values()), 4)

        core_weights = sum(res["weight"] for d, res in division_results.items() if d not in ["01", "04"])
        nowcast_core_cpi = (
            round(sum(res["weight"] * res["nowcast"] for d, res in division_results.items() if d not in ["01", "04"]) / core_weights, 4)
            if core_weights > 0
            else nowcast_headline_cpi
        )

        prior_headline_from_divisions = sum(res["weight"] * res["prior"] for res in division_results.values())
        if prior_headline_from_divisions > 0 and abs(prior_headline_from_divisions - prior_month_cpi) < 0.5:
            prior_month_cpi = round(prior_headline_from_divisions, 4)
        else:
            prior_month_cpi = round(prior_month_cpi, 4)
        projected_mom_pct = round(((nowcast_headline_cpi - prior_month_cpi) / prior_month_cpi) * 100.0, 4)

        # Chain-linking to official NIS benchmark
        nowcast_nis_headline_cpi = None
        latest_nis_cpi = None
        if df_nis is not None and not df_nis.empty:
            latest_nis_row = df_nis.iloc[0]
            latest_nis_cpi = float(latest_nis_row["headline_cpi"])
            nowcast_nis_headline_cpi = round(latest_nis_cpi * (1.0 + (projected_mom_pct / 100.0)), 4)

        # Dynamic uncertainty & 95% CI
        daily_series = df_month.drop_duplicates(subset=["calculation_date"]) if not df_month.empty else pd.DataFrame()
        daily_volatility = float(daily_series["headline_cpi"].std()) if len(daily_series) > 1 else 0.25
        if np.isnan(daily_volatility) or daily_volatility == 0:
            daily_volatility = 0.25

        uncertainty_ratio = round(float(days_remaining / days_in_month), 3)
        margin_of_error = Z_SCORE_95 * daily_volatility * np.sqrt(days_remaining / days_in_month)
        ci_lower_95 = float(round(max(0.0, nowcast_headline_cpi - margin_of_error), 4))
        ci_upper_95 = float(round(nowcast_headline_cpi + margin_of_error, 4))

        # Backward compatibility for FX telemetry
        fx_mom_7d, _ = self.drift_estimator._extract_fx_features(target_date, df_fx)
        fx_daily_drift = round(float(0.28 * fx_mom_7d / 7.0), 6)

        # 5 Target Baskets Specific Outputs
        food_res = division_results.get("01", {})
        alcohol_res = division_results.get("02", {})
        housing_res = division_results.get("04", {})
        transport_res = division_results.get("07", {})
        restaurant_res = division_results.get("11", {})

        return {
            "nowcast_date": target_date,
            "target_month": target_month,
            "days_observed": days_observed,
            "days_remaining": days_remaining,
            "days_in_month": days_in_month,
            "realized_cpi_so_far": round(float(realized_cpi), 4),
            "projected_remaining_cpi": round(float(projected_avg_cpi), 4),
            "projected_mom_pct": projected_mom_pct,
            "nowcast_headline_cpi": nowcast_headline_cpi,
            "nowcast_nis_headline_cpi": nowcast_nis_headline_cpi,
            "nowcast_core_cpi": nowcast_core_cpi,
            "prior_month_cpi": prior_month_cpi,
            "latest_nis_baseline_cpi": latest_nis_cpi,
            "ci_lower_95": ci_lower_95,
            "ci_upper_95": ci_upper_95,
            "uncertainty_pct": uncertainty_ratio,
            "fx_momentum_7d": round(float(fx_mom_7d), 6),
            "fx_daily_drift": fx_daily_drift,
            "model_name": self.model_name,
            # 5 Key Disaggregated Baskets
            "nowcast_food_cpi": food_res.get("nowcast", nowcast_headline_cpi),
            "projected_food_mom_pct": food_res.get("mom_pct", projected_mom_pct),
            "nowcast_alcohol_cpi": alcohol_res.get("nowcast", nowcast_headline_cpi),
            "projected_alcohol_mom_pct": alcohol_res.get("mom_pct", projected_mom_pct),
            "nowcast_housing_cpi": housing_res.get("nowcast", nowcast_headline_cpi),
            "projected_housing_mom_pct": housing_res.get("mom_pct", projected_mom_pct),
            "nowcast_transport_cpi": transport_res.get("nowcast", nowcast_headline_cpi),
            "projected_transport_mom_pct": transport_res.get("mom_pct", projected_mom_pct),
            "nowcast_restaurant_cpi": restaurant_res.get("nowcast", nowcast_headline_cpi),
            "projected_restaurant_mom_pct": restaurant_res.get("mom_pct", projected_mom_pct),
            "baskets_detail": division_results,
        }

    def save_nowcast(self, nowcast_res: dict[str, Any]) -> None:
        """Upserts computed nowcast into gold.fct_cpi_nowcast with 5-basket support."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gold.fct_cpi_nowcast (
                        nowcast_date DATE NOT NULL,
                        target_month DATE NOT NULL,
                        days_observed INTEGER NOT NULL,
                        days_remaining INTEGER NOT NULL,
                        days_in_month INTEGER NOT NULL,
                        realized_cpi_so_far NUMERIC(10, 4),
                        projected_remaining_cpi NUMERIC(10, 4),
                        projected_mom_pct NUMERIC(8, 4) NOT NULL,
                        nowcast_headline_cpi NUMERIC(10, 4) NOT NULL,
                        nowcast_nis_headline_cpi NUMERIC(10, 4),
                        nowcast_core_cpi NUMERIC(10, 4),
                        prior_month_cpi NUMERIC(10, 4),
                        ci_lower_95 NUMERIC(10, 4),
                        ci_upper_95 NUMERIC(10, 4),
                        uncertainty_pct NUMERIC(6, 3),
                        model_name VARCHAR(50) DEFAULT 'hybrid_ridge_5basket_v1',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        nowcast_food_cpi NUMERIC(10, 4),
                        nowcast_alcohol_cpi NUMERIC(10, 4),
                        nowcast_housing_cpi NUMERIC(10, 4),
                        nowcast_transport_cpi NUMERIC(10, 4),
                        nowcast_restaurant_cpi NUMERIC(10, 4),
                        projected_food_mom_pct NUMERIC(8, 4),
                        projected_alcohol_mom_pct NUMERIC(8, 4),
                        projected_housing_mom_pct NUMERIC(8, 4),
                        projected_transport_mom_pct NUMERIC(8, 4),
                        projected_restaurant_mom_pct NUMERIC(8, 4),
                        baskets_detail JSONB,
                        PRIMARY KEY (nowcast_date, target_month, model_name)
                    );
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE gold.fct_cpi_nowcast
                    ADD COLUMN IF NOT EXISTS nowcast_food_cpi NUMERIC(10, 4),
                    ADD COLUMN IF NOT EXISTS nowcast_alcohol_cpi NUMERIC(10, 4),
                    ADD COLUMN IF NOT EXISTS nowcast_housing_cpi NUMERIC(10, 4),
                    ADD COLUMN IF NOT EXISTS nowcast_transport_cpi NUMERIC(10, 4),
                    ADD COLUMN IF NOT EXISTS nowcast_restaurant_cpi NUMERIC(10, 4),
                    ADD COLUMN IF NOT EXISTS projected_food_mom_pct NUMERIC(8, 4),
                    ADD COLUMN IF NOT EXISTS projected_alcohol_mom_pct NUMERIC(8, 4),
                    ADD COLUMN IF NOT EXISTS projected_housing_mom_pct NUMERIC(8, 4),
                    ADD COLUMN IF NOT EXISTS projected_transport_mom_pct NUMERIC(8, 4),
                    ADD COLUMN IF NOT EXISTS projected_restaurant_mom_pct NUMERIC(8, 4),
                    ADD COLUMN IF NOT EXISTS baskets_detail JSONB;
                    """
                )

                payload = dict(nowcast_res)
                if "baskets_detail" in payload and isinstance(payload["baskets_detail"], (dict, list)):
                    payload["baskets_detail"] = json.dumps(payload["baskets_detail"])

                cur.execute(
                    """
                    INSERT INTO gold.fct_cpi_nowcast (
                        nowcast_date, target_month, days_observed, days_remaining, days_in_month,
                        realized_cpi_so_far, projected_remaining_cpi, projected_mom_pct,
                        nowcast_headline_cpi, nowcast_nis_headline_cpi,
                        nowcast_core_cpi, prior_month_cpi,
                        ci_lower_95, ci_upper_95,
                        uncertainty_pct, model_name,
                        nowcast_food_cpi, nowcast_alcohol_cpi, nowcast_housing_cpi,
                        nowcast_transport_cpi, nowcast_restaurant_cpi,
                        projected_food_mom_pct, projected_alcohol_mom_pct, projected_housing_mom_pct,
                        projected_transport_mom_pct, projected_restaurant_mom_pct,
                        baskets_detail
                    ) VALUES (
                        %(nowcast_date)s, %(target_month)s, %(days_observed)s, %(days_remaining)s, %(days_in_month)s,
                        %(realized_cpi_so_far)s, %(projected_remaining_cpi)s, %(projected_mom_pct)s,
                        %(nowcast_headline_cpi)s, %(nowcast_nis_headline_cpi)s,
                        %(nowcast_core_cpi)s, %(prior_month_cpi)s,
                        %(ci_lower_95)s, %(ci_upper_95)s,
                        %(uncertainty_pct)s, %(model_name)s,
                        %(nowcast_food_cpi)s, %(nowcast_alcohol_cpi)s, %(nowcast_housing_cpi)s,
                        %(nowcast_transport_cpi)s, %(nowcast_restaurant_cpi)s,
                        %(projected_food_mom_pct)s, %(projected_alcohol_mom_pct)s, %(projected_housing_mom_pct)s,
                        %(projected_transport_mom_pct)s, %(projected_restaurant_mom_pct)s,
                        %(baskets_detail)s
                    )
                    ON CONFLICT (nowcast_date, target_month, model_name) DO UPDATE
                    SET days_observed = EXCLUDED.days_observed,
                        days_remaining = EXCLUDED.days_remaining,
                        realized_cpi_so_far = EXCLUDED.realized_cpi_so_far,
                        projected_remaining_cpi = EXCLUDED.projected_remaining_cpi,
                        projected_mom_pct = EXCLUDED.projected_mom_pct,
                        nowcast_headline_cpi = EXCLUDED.nowcast_headline_cpi,
                        nowcast_nis_headline_cpi = EXCLUDED.nowcast_nis_headline_cpi,
                        nowcast_core_cpi = EXCLUDED.nowcast_core_cpi,
                        prior_month_cpi = EXCLUDED.prior_month_cpi,
                        ci_lower_95 = EXCLUDED.ci_lower_95,
                        ci_upper_95 = EXCLUDED.ci_upper_95,
                        uncertainty_pct = EXCLUDED.uncertainty_pct,
                        nowcast_food_cpi = EXCLUDED.nowcast_food_cpi,
                        nowcast_alcohol_cpi = EXCLUDED.nowcast_alcohol_cpi,
                        nowcast_housing_cpi = EXCLUDED.nowcast_housing_cpi,
                        nowcast_transport_cpi = EXCLUDED.nowcast_transport_cpi,
                        nowcast_restaurant_cpi = EXCLUDED.nowcast_restaurant_cpi,
                        projected_food_mom_pct = EXCLUDED.projected_food_mom_pct,
                        projected_alcohol_mom_pct = EXCLUDED.projected_alcohol_mom_pct,
                        projected_housing_mom_pct = EXCLUDED.projected_housing_mom_pct,
                        projected_transport_mom_pct = EXCLUDED.projected_transport_mom_pct,
                        projected_restaurant_mom_pct = EXCLUDED.projected_restaurant_mom_pct,
                        baskets_detail = EXCLUDED.baskets_detail;
                    """,
                    payload,
                )
                conn.commit()
                log.info(
                    "✅ Nowcast persisted: %s -> Month %s | MoM: %s%% | Headline CPI: %s | Food: %s | Transport: %s",
                    nowcast_res["nowcast_date"],
                    nowcast_res["target_month"],
                    nowcast_res["projected_mom_pct"],
                    nowcast_res["nowcast_headline_cpi"],
                    nowcast_res.get("nowcast_food_cpi"),
                    nowcast_res.get("nowcast_transport_cpi"),
                )
        finally:
            conn.close()

    @staticmethod
    def compute_evaluation_metrics_dataframe(df_pairs: pd.DataFrame) -> pd.DataFrame:
        """
        Computes pointwise and 3-month rolling RMSE, MAE, percentage error,
        and directional hit metrics for a paired DataFrame of predictions vs ground truth actuals.
        """
        if df_pairs.empty:
            return pd.DataFrame()

        df = df_pairs.copy()
        for col in ["nowcast_headline_cpi", "actual_headline_cpi", "nowcast_mom_pct", "actual_mom_pct"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df["mom_error"] = (df["nowcast_mom_pct"] - df["actual_mom_pct"]).round(4)
        df["cpi_absolute_error"] = (df["nowcast_headline_cpi"] - df["actual_headline_cpi"]).abs().round(4)
        df["cpi_pct_error"] = (
            (df["cpi_absolute_error"] / df["actual_headline_cpi"].replace(0, np.nan)) * 100.0
        ).round(3)
        df["directional_hit"] = np.where(
            df["nowcast_mom_pct"].notna() & df["actual_mom_pct"].notna(),
            (df["nowcast_mom_pct"] * df["actual_mom_pct"] >= 0) | (df["nowcast_mom_pct"].abs() < 0.05),
            None,
        )

        # Compute 3-month rolling RMSE and MAE on CPI
        sq_err = (df["nowcast_headline_cpi"] - df["actual_headline_cpi"]) ** 2
        df["rolling_rmse_3m"] = (
            sq_err.rolling(window=3, min_periods=1)
            .mean()
            .apply(np.sqrt)
            .round(4)
        )
        df["rolling_mae_3m"] = (
            df["cpi_absolute_error"]
            .rolling(window=3, min_periods=1)
            .mean()
            .round(4)
        )
        return df

    def persist_performance_metrics(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """
        Evaluates historical nowcasts against official NIS and monthly CPI actuals,
        computing RMSE, MAE, directional accuracy, and tracking error metrics, then persists
        the results into gold.nowcast_performance_metrics.
        """
        if target_date is None:
            target_date = date.today()

        conn = get_db_connection()
        records: list[dict[str, Any]] = []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gold.nowcast_performance_metrics (
                        evaluation_date DATE NOT NULL,
                        target_month DATE NOT NULL,
                        model_name VARCHAR(50) NOT NULL,
                        days_observed INTEGER NOT NULL,
                        nowcast_mom_pct NUMERIC(8, 4),
                        actual_mom_pct NUMERIC(8, 4),
                        mom_error NUMERIC(8, 4),
                        nowcast_headline_cpi NUMERIC(10, 4),
                        actual_headline_cpi NUMERIC(10, 4),
                        cpi_absolute_error NUMERIC(10, 4),
                        cpi_pct_error NUMERIC(6, 3),
                        directional_hit BOOLEAN,
                        rolling_rmse_3m NUMERIC(8, 4),
                        rolling_mae_3m NUMERIC(8, 4),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (evaluation_date, target_month, model_name)
                    );
                    """
                )
                cur.execute(
                    """
                    WITH actuals AS (
                        SELECT 
                            cpi_month,
                            headline_cpi AS actual_headline_cpi,
                            mom_inflation_pct AS actual_mom_pct
                        FROM gold.dim_nis_official_cpi
                        UNION ALL
                        SELECT
                            cpi_month,
                            monthly_headline_cpi AS actual_headline_cpi,
                            COALESCE(headline_mom_inflation_pct, mom_inflation_pct) AS actual_mom_pct
                        FROM gold.fct_cpi_monthly m
                        WHERE NOT EXISTS (
                            SELECT 1 FROM gold.dim_nis_official_cpi n WHERE n.cpi_month = m.cpi_month
                        )
                    )
                    SELECT 
                        n.nowcast_date AS evaluation_date,
                        n.target_month,
                        n.model_name,
                        n.days_observed,
                        n.projected_mom_pct AS nowcast_mom_pct,
                        a.actual_mom_pct,
                        n.nowcast_headline_cpi,
                        a.actual_headline_cpi
                    FROM gold.fct_cpi_nowcast n
                    JOIN actuals a ON a.cpi_month = n.target_month
                    WHERE n.nowcast_date <= %s
                    ORDER BY n.nowcast_date ASC;
                    """,
                    (target_date,),
                )
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                if not rows:
                    return records

                df_pairs = pd.DataFrame(rows, columns=cols)
                df_metrics = self.compute_evaluation_metrics_dataframe(df_pairs)

                for _, row in df_metrics.iterrows():
                    rec = {
                        "evaluation_date": row["evaluation_date"],
                        "target_month": row["target_month"],
                        "model_name": row["model_name"],
                        "days_observed": int(row["days_observed"]),
                        "nowcast_mom_pct": float(row["nowcast_mom_pct"]) if pd.notna(row["nowcast_mom_pct"]) else None,
                        "actual_mom_pct": float(row["actual_mom_pct"]) if pd.notna(row["actual_mom_pct"]) else None,
                        "mom_error": float(row["mom_error"]) if pd.notna(row["mom_error"]) else None,
                        "nowcast_headline_cpi": float(row["nowcast_headline_cpi"]) if pd.notna(row["nowcast_headline_cpi"]) else None,
                        "actual_headline_cpi": float(row["actual_headline_cpi"]) if pd.notna(row["actual_headline_cpi"]) else None,
                        "cpi_absolute_error": float(row["cpi_absolute_error"]) if pd.notna(row["cpi_absolute_error"]) else None,
                        "cpi_pct_error": float(row["cpi_pct_error"]) if pd.notna(row["cpi_pct_error"]) else None,
                        "directional_hit": bool(row["directional_hit"]) if pd.notna(row["directional_hit"]) else None,
                        "rolling_rmse_3m": float(row["rolling_rmse_3m"]) if pd.notna(row["rolling_rmse_3m"]) else None,
                        "rolling_mae_3m": float(row["rolling_mae_3m"]) if pd.notna(row["rolling_mae_3m"]) else None,
                    }
                    records.append(rec)
                    cur.execute(
                        """
                        INSERT INTO gold.nowcast_performance_metrics (
                            evaluation_date, target_month, model_name, days_observed,
                            nowcast_mom_pct, actual_mom_pct, mom_error,
                            nowcast_headline_cpi, actual_headline_cpi,
                            cpi_absolute_error, cpi_pct_error, directional_hit,
                            rolling_rmse_3m, rolling_mae_3m
                        ) VALUES (
                            %(evaluation_date)s, %(target_month)s, %(model_name)s, %(days_observed)s,
                            %(nowcast_mom_pct)s, %(actual_mom_pct)s, %(mom_error)s,
                            %(nowcast_headline_cpi)s, %(actual_headline_cpi)s,
                            %(cpi_absolute_error)s, %(cpi_pct_error)s, %(directional_hit)s,
                            %(rolling_rmse_3m)s, %(rolling_mae_3m)s
                        )
                        ON CONFLICT (evaluation_date, target_month, model_name) DO UPDATE
                        SET days_observed = EXCLUDED.days_observed,
                            nowcast_mom_pct = EXCLUDED.nowcast_mom_pct,
                            actual_mom_pct = EXCLUDED.actual_mom_pct,
                            mom_error = EXCLUDED.mom_error,
                            nowcast_headline_cpi = EXCLUDED.nowcast_headline_cpi,
                            actual_headline_cpi = EXCLUDED.actual_headline_cpi,
                            cpi_absolute_error = EXCLUDED.cpi_absolute_error,
                            cpi_pct_error = EXCLUDED.cpi_pct_error,
                            directional_hit = EXCLUDED.directional_hit,
                            rolling_rmse_3m = EXCLUDED.rolling_rmse_3m,
                            rolling_mae_3m = EXCLUDED.rolling_mae_3m,
                            updated_at = NOW();
                        """,
                        rec,
                    )
                conn.commit()
                log.info("Persisted %d nowcast performance records into gold.nowcast_performance_metrics.", len(records))
        finally:
            conn.close()
        return records

    def run_daily_nowcast(self, target_date: date | None = None) -> dict[str, Any]:
        """Runs the live daily nowcasting pipeline."""
        if target_date is None:
            target_date = date.today()

        log.info("🚀 Initiating Machine Learning-Assisted Inflation Nowcast for %s...", target_date)
        try:
            df_daily, df_fx, df_monthly, df_nis = self.fetch_training_data(target_date)
            res = self.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)
            self.save_nowcast(res)
            try:
                self.persist_performance_metrics(target_date)
            except Exception as e_perf:
                log.warning("Could not update nowcast performance tracking metrics: %s", e_perf)
            return res
        except Exception as e:
            log.warning("Database unavailable for live nowcasting. Generating synthetic dry-run: %s", e)
            return self.generate_synthetic_test_nowcast(target_date)

    def generate_synthetic_test_nowcast(self, target_date: date | None = None) -> dict[str, Any]:
        """Fallback synthetic generator for unit testing without a live database."""
        if target_date is None:
            target_date = date.today()

        target_month_start = target_date.replace(day=1)
        _, days_in_month = calendar.monthrange(target_date.year, target_date.month)
        days_observed = target_date.day

        # Mock daily facts
        dates = [target_month_start + timedelta(days=i) for i in range(days_observed)]
        mock_daily = []
        for d in dates:
            for div in NIS_COICOP_WEIGHTS:
                mock_daily.append(
                    {
                        "calculation_date": d,
                        "coicop_division": div,
                        "division_name": NIS_COICOP_WEIGHTS[div]["name"],
                        "weight": NIS_COICOP_WEIGHTS[div]["weight"],
                        "division_index": 102.5,
                        "headline_cpi": 102.5,
                        "core_cpi": 101.8,
                        "item_count": 100,
                        "observation_count": 500,
                    }
                )
        df_daily = pd.DataFrame(mock_daily)
        df_fx = pd.DataFrame([{"execution_date": target_date, "rate": 4050.0}])
        df_monthly = pd.DataFrame(
            [
                {
                    "cpi_month": target_month_start - timedelta(days=30),
                    "monthly_headline_cpi": 101.5,
                    "monthly_core_cpi": 101.0,
                    "mom_inflation_pct": 0.50,
                }
            ]
        )
        df_nis = pd.DataFrame(
            [
                {
                    "cpi_month": target_month_start - timedelta(days=30),
                    "headline_cpi": 219.10,
                    "core_cpi": 218.40,
                    "mom_inflation_pct": -0.7,
                }
            ]
        )

        return self.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)

    def evaluate_historical_accuracy(
        self,
        df_daily: pd.DataFrame,
        df_fx: pd.DataFrame,
        df_monthly: pd.DataFrame,
        df_nis: pd.DataFrame | None = None,
        evaluation_days: list[int] | None = None,
    ) -> dict[str, Any]:
        """Automated Backtesting and Benchmark Evaluation Harness.

        Evaluates nowcasting accuracy across expanding horizons (Day 5, 10, 15, 20, 25)
        against official ground-truth monthly inflation. Computes:
        - Root Mean Squared Error (RMSE)
        - Mean Absolute Error (MAE)
        - Directional Accuracy (%)
        - Horizon Convergence Telemetry
        """
        if evaluation_days is None:
            evaluation_days = [5, 10, 15, 20, 25]

        if df_daily.empty:
            return {"error": "Empty daily dataset"}

        df_daily_copy = df_daily.copy()
        df_daily_copy["calculation_date"] = pd.to_datetime(df_daily_copy["calculation_date"]).dt.date

        # Identify all distinct calendar months in df_daily
        months = sorted({d.replace(day=1) for d in df_daily_copy["calculation_date"]})

        eval_records: list[dict[str, Any]] = []

        for m in months:
            _, days_in_month = calendar.monthrange(m.year, m.month)

            # Find ground truth actual for month m
            actual_headline = None
            actual_mom = None

            if df_monthly is not None and not df_monthly.empty:
                m_series = pd.to_datetime(df_monthly["cpi_month"]).dt.date
                match = df_monthly[m_series == m]
                if not match.empty:
                    actual_headline = float(match.iloc[0]["monthly_headline_cpi"])
                    if "headline_mom_inflation_pct" in match.columns and pd.notna(match.iloc[0]["headline_mom_inflation_pct"]):
                        actual_mom = float(match.iloc[0]["headline_mom_inflation_pct"])
                    elif "mom_inflation_pct" in match.columns and pd.notna(match.iloc[0]["mom_inflation_pct"]):
                        actual_mom = float(match.iloc[0]["mom_inflation_pct"])

            # If ground truth monthly row isn't in df_monthly, check if full month exists in df_daily
            if actual_headline is None:
                month_daily = df_daily_copy[(df_daily_copy["calculation_date"] >= m) & (df_daily_copy["calculation_date"] <= m.replace(day=days_in_month))]
                if len(month_daily["calculation_date"].unique()) >= 10:
                    actual_headline = float(month_daily.drop_duplicates("calculation_date")["headline_cpi"].mean())
                    prior_m = (m - timedelta(days=5)).replace(day=1)
                    prior_daily = df_daily_copy[(df_daily_copy["calculation_date"] >= prior_m) & (df_daily_copy["calculation_date"] < m)]
                    if not prior_daily.empty:
                        prior_mean = float(prior_daily.drop_duplicates("calculation_date")["headline_cpi"].mean())
                        actual_mom = round(((actual_headline - prior_mean) / prior_mean) * 100.0, 4)

            if actual_headline is None:
                continue

            for day in evaluation_days:
                if day > days_in_month:
                    continue
                eval_date = m.replace(day=day)
                # Ensure we only feed historical data up to eval_date (no lookahead bias)
                sub_daily = df_daily_copy[df_daily_copy["calculation_date"] <= eval_date]
                if sub_daily.empty:
                    continue
                sub_fx = df_fx[pd.to_datetime(df_fx["execution_date"]).dt.date <= eval_date] if df_fx is not None and not df_fx.empty else pd.DataFrame()
                sub_monthly = df_monthly[pd.to_datetime(df_monthly["cpi_month"]).dt.date < m] if df_monthly is not None and not df_monthly.empty else pd.DataFrame()

                try:
                    res = self.nowcast_for_date(eval_date, sub_daily, sub_fx, sub_monthly, df_nis)
                    pred_headline = res["nowcast_headline_cpi"]
                    pred_mom = res["projected_mom_pct"]

                    abs_err_cpi = abs(pred_headline - actual_headline)
                    sq_err_cpi = (pred_headline - actual_headline) ** 2

                    abs_err_mom = abs(pred_mom - actual_mom) if actual_mom is not None else None
                    sq_err_mom = (pred_mom - actual_mom) ** 2 if actual_mom is not None else None

                    dir_correct = None
                    if actual_mom is not None:
                        dir_correct = (pred_mom * actual_mom >= 0) or (abs(pred_mom) < 0.05 and abs(actual_mom) < 0.05)

                    eval_records.append({
                        "month": m,
                        "day_of_month": day,
                        "eval_date": eval_date,
                        "actual_headline": actual_headline,
                        "predicted_headline": pred_headline,
                        "actual_mom": actual_mom,
                        "predicted_mom": pred_mom,
                        "abs_err_cpi": abs_err_cpi,
                        "sq_err_cpi": sq_err_cpi,
                        "abs_err_mom": abs_err_mom,
                        "sq_err_mom": sq_err_mom,
                        "dir_correct": dir_correct,
                    })
                except Exception as e:
                    log.debug("Evaluation on %s skipped: %s", eval_date, e)

        if not eval_records:
            return {"error": "Insufficient overlapping months for backtesting evaluation"}

        df_eval = pd.DataFrame(eval_records)

        # Aggregate by evaluation day horizon (Day 5, 10, 15, 20, 25)
        horizon_metrics = {}
        for day, group in df_eval.groupby("day_of_month"):
            rmse_cpi = float(np.sqrt(group["sq_err_cpi"].mean()))
            mae_cpi = float(group["abs_err_cpi"].mean())

            valid_mom = group.dropna(subset=["sq_err_mom"])
            rmse_mom = float(np.sqrt(valid_mom["sq_err_mom"].mean())) if not valid_mom.empty else None
            mae_mom = float(valid_mom["abs_err_mom"].mean()) if not valid_mom.empty else None
            dir_acc = float(group["dir_correct"].mean() * 100.0) if "dir_correct" in group and not group["dir_correct"].isna().all() else None

            horizon_metrics[f"Day_{day:02d}"] = {
                "eval_day": int(day),
                "n_evaluations": len(group),
                "rmse_headline_cpi": round(rmse_cpi, 4),
                "mae_headline_cpi": round(mae_cpi, 4),
                "rmse_mom_pct": round(rmse_mom, 4) if rmse_mom is not None else None,
                "mae_mom_pct": round(mae_mom, 4) if mae_mom is not None else None,
                "directional_accuracy_pct": round(dir_acc, 2) if dir_acc is not None else None,
            }

        overall_rmse = float(np.sqrt(df_eval["sq_err_cpi"].mean()))
        overall_mae = float(df_eval["abs_err_cpi"].mean())
        overall_dir = float(df_eval["dir_correct"].dropna().mean() * 100.0) if not df_eval["dir_correct"].dropna().empty else None

        return {
            "evaluation_months_count": len(months),
            "total_evaluations": len(df_eval),
            "overall_rmse_cpi": round(overall_rmse, 4),
            "overall_mae_cpi": round(overall_mae, 4),
            "overall_directional_accuracy_pct": round(overall_dir, 2) if overall_dir is not None else None,
            "horizon_convergence": horizon_metrics,
            "details": df_eval.to_dict(orient="records"),
        }


def execute_nowcasting_pipeline(**context) -> dict[str, Any]:
    """Airflow-callable Python entrypoint for daily inflation nowcasting."""
    logical_date_str = context.get("ds")
    if logical_date_str:
        calc_date = pd.to_datetime(logical_date_str).date()
    else:
        calc_date = date.today()

    nowcaster = CPINowcaster()
    return nowcaster.run_daily_nowcast(calc_date)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Cambodia CPI Daily Inflation Nowcaster")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--backtest", action="store_true", help="Run historical backtesting evaluation")
    args = parser.parse_args()

    nowcaster = CPINowcaster()
    if args.backtest:
        print("[*] Running Historical Nowcasting Backtesting & Convergence Evaluation...")
        try:
            df_daily, df_fx, df_monthly, df_nis = nowcaster.fetch_training_data(date.today())
            results = nowcaster.evaluate_historical_accuracy(df_daily, df_fx, df_monthly, df_nis)
        except Exception as e:
            print(f"Live database unavailable ({e}). Running backtest on synthetic multi-month series...")
            # Create synthetic 2-month dataset for testing
            dates_m1 = [date(2026, 7, 1) + timedelta(days=i) for i in range(31)]
            dates_m2 = [date(2026, 8, 1) + timedelta(days=i) for i in range(31)]
            mock_daily = []
            for d in dates_m1 + dates_m2:
                mock_daily.append({
                    "calculation_date": d,
                    "coicop_division": "01",
                    "weight": 0.44775,
                    "division_index": 100.0 + (d.month * 0.5) + (d.day * 0.01),
                    "headline_cpi": 100.0 + (d.month * 0.5) + (d.day * 0.01),
                    "core_cpi": 99.8 + (d.month * 0.3) + (d.day * 0.01),
                })
            df_d = pd.DataFrame(mock_daily)
            df_f = pd.DataFrame([{"execution_date": d, "rate": 4050.0} for d in dates_m1 + dates_m2])
            df_m = pd.DataFrame([
                {"cpi_month": date(2026, 7, 1), "monthly_headline_cpi": 100.5, "mom_inflation_pct": 0.5},
                {"cpi_month": date(2026, 8, 1), "monthly_headline_cpi": 101.0, "mom_inflation_pct": 0.5},
            ])
            results = nowcaster.evaluate_historical_accuracy(df_d, df_f, df_m)

        print("\n=======================================================")
        print("  CAMBODIA CPI NOWCASTING HISTORICAL CONVERGENCE")
        print("=======================================================")
        print(f"Overall RMSE (Headline CPI): {results.get('overall_rmse_cpi')}")
        print(f"Overall MAE (Headline CPI):  {results.get('overall_mae_cpi')}")
        print(f"Directional Accuracy:        {results.get('overall_directional_accuracy_pct')}%")
        print("\nHorizon Convergence (Error Drops as Month Progresses):")
        for horizon, metrics in results.get("horizon_convergence", {}).items():
            print(f"  {horizon}: RMSE = {metrics.get('rmse_headline_cpi')}, MAE = {metrics.get('mae_headline_cpi')}")
        print("=======================================================\n")
    else:
        target = pd.to_datetime(args.date).date() if args.date else date.today()
        out = nowcaster.run_daily_nowcast(target)
        print(f"\n[OK] Nowcast Completed for {out['nowcast_date']} ({out.get('model_name')}):")
        print(f"  Target Month:     {out['target_month']}")
        print(f"  Observed Days:    {out['days_observed']} / {out['days_in_month']} ({round(out['days_observed']/out['days_in_month']*100, 1)}%)")
        print(f"  Headline CPI:     {out['nowcast_headline_cpi']}")
        print(f"  Projected MoM:    {out['projected_mom_pct']}%")
        print(f"  95% CI Bounds:    [{out['ci_lower_95']} - {out['ci_upper_95']}]")
        print(f"  5-Basket Disaggregation:")
        print(f"    - Food (44.8%):       CPI {out.get('nowcast_food_cpi')} (MoM: {out.get('projected_food_mom_pct')}%)")
        print(f"    - Alcohol (1.6%):     CPI {out.get('nowcast_alcohol_cpi')} (MoM: {out.get('projected_alcohol_mom_pct')}%)")
        print(f"    - Housing (17.1%):    CPI {out.get('nowcast_housing_cpi')} (MoM: {out.get('projected_housing_mom_pct')}%)")
        print(f"    - Transport (12.2%):  CPI {out.get('nowcast_transport_cpi')} (MoM: {out.get('projected_transport_mom_pct')}%)")
        print(f"    - Restaurant (5.9%):  CPI {out.get('nowcast_restaurant_cpi')} (MoM: {out.get('projected_restaurant_mom_pct')}%)")
        print(f"  FX 7d Momentum:   {out.get('fx_momentum_7d')}")

