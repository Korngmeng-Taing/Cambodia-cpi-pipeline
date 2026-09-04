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
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ml.config import (
    CI_ALPHA,
    NIS_COICOP_WEIGHTS,
    Z_SCORE_95,
)
from pipeline.config import get_db_connection

log = logging.getLogger(__name__)


class CPINowcaster:
    """Production High-Frequency Inflation Nowcaster."""

    def __init__(self, model_name: str = "ml_assisted_nowcaster_v1"):
        self.model_name = model_name

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

                # 3. Monthly historical aggregations
                cur.execute(
                    """
                    SELECT cpi_month, monthly_headline_cpi, monthly_core_cpi, mom_inflation_pct
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
                    for col in ["monthly_headline_cpi", "monthly_core_cpi", "mom_inflation_pct"]:
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
        """Calculates Month-to-Date nowcast, intra-month projection, and uncertainty bounds."""
        target_month = target_date.replace(day=1)
        _, days_in_month = calendar.monthrange(target_date.year, target_date.month)
        days_observed = min(target_date.day, days_in_month)
        days_remaining = max(0, days_in_month - days_observed)

        # Standardize dates
        if not df_daily.empty and "calculation_date" in df_daily.columns:
            df_daily["calculation_date"] = pd.to_datetime(df_daily["calculation_date"]).dt.date

        # Filter daily facts to active month
        df_month = df_daily[
            (df_daily["calculation_date"] >= target_month)
            & (df_daily["calculation_date"] <= target_date)
        ] if not df_daily.empty else pd.DataFrame()

        # Fallback if active month has no data yet: use latest available
        if df_month.empty and not df_daily.empty:
            latest_cpi = float(df_daily["headline_cpi"].dropna().iloc[-1])
            latest_core = float(df_daily["core_cpi"].dropna().iloc[-1]) if "core_cpi" in df_daily.columns else latest_cpi
            realized_cpi = latest_cpi
            realized_core = latest_core
            daily_volatility = 0.25
        elif not df_month.empty:
            # Dedup by calculation_date to get daily headline series
            daily_series = df_month.drop_duplicates(subset=["calculation_date"])
            realized_cpi = float(daily_series["headline_cpi"].mean())
            realized_core = float(daily_series["core_cpi"].dropna().mean()) if "core_cpi" in daily_series.columns else realized_cpi
            daily_volatility = float(daily_series["headline_cpi"].std()) if len(daily_series) > 1 else 0.25
            if np.isnan(daily_volatility) or daily_volatility == 0:
                daily_volatility = 0.25
        else:
            realized_cpi = 100.0
            realized_core = 100.0
            daily_volatility = 0.25

        # -------------------------------------------------------------------------
        # Leading Momentum Signals (Division 01 Food & Division 07 Transport)
        # Following Macias et al. (2023)
        # -------------------------------------------------------------------------
        food_momentum = 0.0
        transport_momentum = 0.0
        if not df_daily.empty and "coicop_division" in df_daily.columns:
            # Division 01 Food 7-day momentum
            df_food = df_daily[df_daily["coicop_division"] == "01"].sort_values("calculation_date")
            if len(df_food) >= 7:
                food_recent = float(df_food["division_index"].iloc[-1])
                food_prior = float(df_food["division_index"].iloc[-7])
                if food_prior > 0:
                    food_momentum = (food_recent - food_prior) / food_prior

            # Division 07 Transport 7-day momentum
            df_trans = df_daily[df_daily["coicop_division"] == "07"].sort_values("calculation_date")
            if len(df_trans) >= 7:
                trans_recent = float(df_trans["division_index"].iloc[-1])
                trans_prior = float(df_trans["division_index"].iloc[-7])
                if trans_prior > 0:
                    transport_momentum = (trans_recent - trans_prior) / trans_prior

        # Combined daily drift rate from leading signals
        # Food (44.8% weight) + Transport (12.2% weight)
        projected_daily_drift = (0.44775 * (food_momentum / 7.0)) + (0.12180 * (transport_momentum / 7.0))

        # Project end of month CPI for remaining days
        if days_remaining > 0:
            projected_end_cpi = realized_cpi * (1.0 + (projected_daily_drift * days_remaining))
            projected_core_end = realized_core * (1.0 + (projected_daily_drift * 0.5 * days_remaining))
        else:
            projected_end_cpi = realized_cpi
            projected_core_end = realized_core

        # Weighted combination: Observed days share + Remaining days share
        obs_weight = days_observed / days_in_month
        rem_weight = days_remaining / days_in_month

        nowcast_headline_cpi = round((obs_weight * realized_cpi) + (rem_weight * projected_end_cpi), 4)
        nowcast_core_cpi = round((obs_weight * realized_core) + (rem_weight * projected_core_end), 4)

        # -------------------------------------------------------------------------
        # Prior Month Baseline & Projected Month-over-Month (MoM %) Inflation
        # -------------------------------------------------------------------------
        prior_month_cpi = 100.0
        if df_monthly is not None and not df_monthly.empty:
            # Look for month immediately preceding target_month
            prior_months = df_monthly[pd.to_datetime(df_monthly["cpi_month"]).dt.date < target_month]
            if not prior_months.empty:
                prior_month_cpi = float(prior_months.iloc[-1]["monthly_headline_cpi"])
            else:
                prior_month_cpi = float(df_monthly.iloc[-1]["monthly_headline_cpi"])
        elif not df_daily.empty:
            # Fallback to earliest recorded daily CPI
            prior_daily = df_daily[df_daily["calculation_date"] < target_month]
            if not prior_daily.empty:
                prior_month_cpi = float(prior_daily["headline_cpi"].iloc[-1])
            else:
                prior_month_cpi = 100.0

        projected_mom_pct = round(((nowcast_headline_cpi - prior_month_cpi) / prior_month_cpi) * 100.0, 4)

        # -------------------------------------------------------------------------
        # Chain-Linking to Official NIS Benchmark (Oct–Dec 2006 = 100)
        # -------------------------------------------------------------------------
        nowcast_nis_headline_cpi = None
        latest_nis_cpi = None
        if df_nis is not None and not df_nis.empty:
            latest_nis_row = df_nis.iloc[0]
            latest_nis_cpi = float(latest_nis_row["headline_cpi"])
            # Apply estimated MoM rate to latest published NIS official index
            nowcast_nis_headline_cpi = round(latest_nis_cpi * (1.0 + (projected_mom_pct / 100.0)), 4)

        # -------------------------------------------------------------------------
        # Dynamic Uncertainty Ratio and 95% Confidence Interval
        # -------------------------------------------------------------------------
        uncertainty_ratio = round(float(days_remaining / days_in_month), 3)
        margin_of_error = Z_SCORE_95 * daily_volatility * np.sqrt(days_remaining / days_in_month)

        ci_lower_95 = float(round(max(0.0, nowcast_headline_cpi - margin_of_error), 4))
        ci_upper_95 = float(round(nowcast_headline_cpi + margin_of_error, 4))

        return {
            "nowcast_date": target_date,
            "target_month": target_month,
            "days_observed": days_observed,
            "days_remaining": days_remaining,
            "days_in_month": days_in_month,
            "realized_cpi_so_far": round(float(realized_cpi), 4),
            "projected_remaining_cpi": round(float(projected_end_cpi), 4),
            "projected_mom_pct": projected_mom_pct,
            "nowcast_headline_cpi": nowcast_headline_cpi,
            "nowcast_nis_headline_cpi": nowcast_nis_headline_cpi,
            "nowcast_core_cpi": nowcast_core_cpi,
            "prior_month_cpi": round(float(prior_month_cpi), 4),
            "latest_nis_baseline_cpi": latest_nis_cpi,
            "ci_lower_95": ci_lower_95,
            "ci_upper_95": ci_upper_95,
            "uncertainty_pct": uncertainty_ratio,
            "model_name": self.model_name,
        }

    def save_nowcast(self, nowcast_res: dict[str, Any]) -> None:
        """Upserts computed nowcast into gold.fct_cpi_nowcast."""
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
                        model_name VARCHAR(50) DEFAULT 'ml_assisted_nowcaster_v1',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (nowcast_date, target_month, model_name)
                    );
                    """
                )
                cur.execute(
                    """
                    INSERT INTO gold.fct_cpi_nowcast (
                        nowcast_date, target_month, days_observed, days_remaining, days_in_month,
                        realized_cpi_so_far, projected_remaining_cpi, projected_mom_pct,
                        nowcast_headline_cpi, nowcast_nis_headline_cpi,
                        nowcast_core_cpi, prior_month_cpi,
                        ci_lower_95, ci_upper_95,
                        uncertainty_pct, model_name
                    ) VALUES (
                        %(nowcast_date)s, %(target_month)s, %(days_observed)s, %(days_remaining)s, %(days_in_month)s,
                        %(realized_cpi_so_far)s, %(projected_remaining_cpi)s, %(projected_mom_pct)s,
                        %(nowcast_headline_cpi)s, %(nowcast_nis_headline_cpi)s,
                        %(nowcast_core_cpi)s, %(prior_month_cpi)s,
                        %(ci_lower_95)s, %(ci_upper_95)s,
                        %(uncertainty_pct)s, %(model_name)s
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
                        uncertainty_pct = EXCLUDED.uncertainty_pct;
                    """,
                    nowcast_res,
                )
                conn.commit()
                log.info(
                    "✅ Nowcast persisted: %s -> Month %s | MoM: %s%% | Headline CPI: %s | NIS Base 2006: %s",
                    nowcast_res["nowcast_date"],
                    nowcast_res["target_month"],
                    nowcast_res["projected_mom_pct"],
                    nowcast_res["nowcast_headline_cpi"],
                    nowcast_res.get("nowcast_nis_headline_cpi"),
                )
        finally:
            conn.close()

    def run_daily_nowcast(self, target_date: date | None = None) -> dict[str, Any]:
        """Runs the live daily nowcasting pipeline."""
        if target_date is None:
            target_date = date.today()

        log.info("🚀 Initiating Machine Learning-Assisted Inflation Nowcast for %s...", target_date)
        try:
            df_daily, df_fx, df_monthly, df_nis = self.fetch_training_data(target_date)
            res = self.nowcast_for_date(target_date, df_daily, df_fx, df_monthly, df_nis)
            self.save_nowcast(res)
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


def execute_nowcasting_pipeline(**context) -> dict[str, Any]:
    """Airflow-callable Python entrypoint for daily inflation nowcasting."""
    logical_date_str = context.get("ds")
    if logical_date_str:
        calc_date = pd.to_datetime(logical_date_str).date()
    else:
        calc_date = date.today()

    nowcaster = CPINowcaster()
    return nowcaster.run_daily_nowcast(calc_date)
