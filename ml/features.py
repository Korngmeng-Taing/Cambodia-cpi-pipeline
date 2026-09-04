"""
ml/features.py
──────────────
High-Frequency Feature Engineering Engine for Machine Learning Inflation Forecasting.

Extracts:
1. Day-over-Day price returns and multi-horizon autoregressive lags.
2. Short, medium, and long-term moving averages (MA7, MA14, MA30) and volatility (sigma7, sigma14).
3. Cross-division leading signals (Food 01 and Transport 07 momentum).
4. Cambodian cultural expenditure festival indicators (Khmer New Year, Pchum Ben, Water Festival).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ml.config import (
    CAMBODIA_ANNUAL_HOLIDAYS,
    FEATURE_WINDOWS,
    FORECAST_HORIZONS,
    ML_LAG_INTERVALS,
    NIS_COICOP_WEIGHTS,
)


def get_holiday_features(target_date: date) -> dict[str, int]:
    """Returns binary flags indicating proximity to major Cambodian expenditure festivals."""
    month = target_date.month
    day = target_date.day

    is_holiday = 0
    holiday_name = "none"

    for h in CAMBODIA_ANNUAL_HOLIDAYS:
        if h["month"] == month:
            peak_days = h["peak_days"]
            window = h.get("window_days", 3)
            min_day = max(1, min(peak_days) - window)
            max_day = min(31, max(peak_days) + window)
            if min_day <= day <= max_day:
                is_holiday = 1
                holiday_name = h["name"]
                break

    return {
        "is_holiday_window": is_holiday,
        "is_khmer_new_year": int(month == 4 and 10 <= day <= 20),
        "is_pchum_ben": int(month in (9, 10) and is_holiday == 1 and "Pchum" in holiday_name),
        "is_water_festival": int(month == 11 and is_holiday == 1 and "Water" in holiday_name),
    }




def extract_daily_forecasting_features(
    df_daily: pd.DataFrame, forward_days: int = 30
) -> pd.DataFrame:
    """
    Constructs an end-to-end high-frequency feature matrix from gold.fct_cpi_daily facts.
    Aggregates division-level observations per date, calculates lags, moving averages,
    volatilities, cross-division leading signals, and the forward inflation target.
    """
    if df_daily is None or df_daily.empty:
        return pd.DataFrame()

    df = df_daily.copy()

    # If df_daily contains multi-row division observations per calculation_date, pivot/aggregate
    if "coicop_division" in df.columns and "calculation_date" in df.columns:
        # Standardize types
        for col in ["headline_cpi", "core_cpi", "division_index", "weight"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        agg_df = (
            df.groupby("calculation_date")
            .agg(
                headline_cpi=("headline_cpi", "max"),
                core_cpi=("core_cpi", "max"),
                food_index=(
                    "division_index",
                    lambda s: s[df.loc[s.index, "coicop_division"] == "01"].max()
                    if (df.loc[s.index, "coicop_division"] == "01").any()
                    else np.nan,
                ),
                housing_index=(
                    "division_index",
                    lambda s: s[df.loc[s.index, "coicop_division"] == "04"].max()
                    if (df.loc[s.index, "coicop_division"] == "04").any()
                    else np.nan,
                ),
                transport_index=(
                    "division_index",
                    lambda s: s[df.loc[s.index, "coicop_division"] == "07"].max()
                    if (df.loc[s.index, "coicop_division"] == "07").any()
                    else np.nan,
                ),
            )
            .reset_index()
        )
    else:
        agg_df = df.copy()

    agg_df["calculation_date"] = pd.to_datetime(agg_df["calculation_date"])
    agg_df = agg_df.sort_values("calculation_date").reset_index(drop=True)

    # Fill division fallback if missing
    for div_col in ["food_index", "housing_index", "transport_index"]:
        if div_col in agg_df.columns:
            agg_df[div_col] = agg_df[div_col].fillna(agg_df["headline_cpi"])
        else:
            agg_df[div_col] = agg_df["headline_cpi"]

    # 1. Base Daily Returns (DoD %)
    agg_df["dod_pct"] = agg_df["headline_cpi"].pct_change() * 100.0
    agg_df["food_dod_pct"] = agg_df["food_index"].pct_change() * 100.0
    agg_df["transport_dod_pct"] = agg_df["transport_index"].pct_change() * 100.0

    # Fill initial NaN in returns
    agg_df["dod_pct"] = agg_df["dod_pct"].fillna(0.0)
    agg_df["food_dod_pct"] = agg_df["food_dod_pct"].fillna(0.0)
    agg_df["transport_dod_pct"] = agg_df["transport_dod_pct"].fillna(0.0)

    # 2. Autoregressive Lags (Shifted by 1 so no look-ahead bias!)
    for lag in ML_LAG_INTERVALS:
        agg_df[f"lag_{lag}_dod"] = agg_df["dod_pct"].shift(lag)

    # 3. Moving Averages & Trend Indicators
    agg_df["ma_7"] = agg_df["headline_cpi"].shift(1).rolling(7, min_periods=1).mean()
    agg_df["ma_14"] = agg_df["headline_cpi"].shift(1).rolling(14, min_periods=1).mean()
    agg_df["ma_30"] = agg_df["headline_cpi"].shift(1).rolling(30, min_periods=1).mean()

    # Trend Momentum: relative velocity between short and medium moving averages
    agg_df["momentum_7_30"] = (
        (agg_df["ma_7"] - agg_df["ma_30"]) / agg_df["ma_30"] * 100.0
    ).fillna(0.0)

    # 4. Rolling Volatility
    agg_df["volatility_7d"] = agg_df["dod_pct"].shift(1).rolling(7, min_periods=2).std().fillna(0.0)
    agg_df["volatility_14d"] = agg_df["dod_pct"].shift(1).rolling(14, min_periods=2).std().fillna(0.0)

    # 5. Division Leading Signals (7-day cumulative momentum)
    agg_df["food_momentum_7d"] = (
        agg_df["food_index"].pct_change(7).shift(1) * 100.0
    ).fillna(0.0)
    agg_df["transport_momentum_7d"] = (
        agg_df["transport_index"].pct_change(7).shift(1) * 100.0
    ).fillna(0.0)

    # 6. Calendar & Seasonality
    agg_df["day_of_week"] = agg_df["calculation_date"].dt.dayofweek
    agg_df["is_weekend"] = agg_df["day_of_week"].isin([5, 6]).astype(int)
    agg_df["day_of_month"] = agg_df["calculation_date"].dt.day
    agg_df["month_sin"] = np.sin(2 * np.pi * agg_df["calculation_date"].dt.month / 12)
    agg_df["month_cos"] = np.cos(2 * np.pi * agg_df["calculation_date"].dt.month / 12)

    # Holiday indicators
    holiday_rows = [get_holiday_features(d.date()) for d in agg_df["calculation_date"]]
    df_holidays = pd.DataFrame(holiday_rows)
    for col in df_holidays.columns:
        agg_df[col] = df_holidays[col].values

    # 7. Supervised Target: Cumulative Inflation over next forward_days
    # target = ((CPI_{t + H} - CPI_t) / CPI_t) * 100
    if forward_days > 0:
        agg_df["target"] = (
            (agg_df["headline_cpi"].shift(-forward_days) - agg_df["headline_cpi"])
            / agg_df["headline_cpi"]
        ) * 100.0

    return agg_df


