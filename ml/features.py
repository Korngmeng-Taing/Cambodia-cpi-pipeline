"""
ml/features.py
──────────────
High-Frequency Feature Engineering Engine for Inflation Nowcasting.

Extracts:
1. Intra-month realized price averages and elapsed completion ratios.
2. Short, medium, and long-term moving averages (MA7, MA14, MA30) and volatility (sigma14).
3. MEF official USD/KHR exchange rate momentum (DoD and 7-day relative changes).
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


def extract_nowcasting_features(
    target_date: date,
    df_daily_cpi: pd.DataFrame,
    df_exchange_rates: pd.DataFrame | None = None,
    df_monthly_cpi: pd.DataFrame | None = None,
    df_nis_official: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Constructs a comprehensive feature vector for target_date within its month.
    Extracts intra-month scraped signals, macroeconomic indicators, and official NIS anchors.
    """
    target_month_start = target_date.replace(day=1)
    _, total_days_in_month = calendar.monthrange(target_date.year, target_date.month)
    days_observed = target_date.day
    days_remaining = total_days_in_month - days_observed
    observed_ratio = float(days_observed / total_days_in_month)

    # Ensure numeric columns are cast to float from database Decimals
    if df_daily_cpi is not None and not df_daily_cpi.empty:
        df_daily_cpi = df_daily_cpi.copy()
        for col in ["headline_cpi", "core_cpi", "division_index", "weight"]:
            if col in df_daily_cpi.columns:
                df_daily_cpi[col] = pd.to_numeric(df_daily_cpi[col], errors="coerce")

    if df_exchange_rates is not None and not df_exchange_rates.empty:
        df_exchange_rates = df_exchange_rates.copy()
        if "rate" in df_exchange_rates.columns:
            df_exchange_rates["rate"] = pd.to_numeric(df_exchange_rates["rate"], errors="coerce")

    if df_monthly_cpi is not None and not df_monthly_cpi.empty:
        df_monthly_cpi = df_monthly_cpi.copy()
        for col in ["monthly_headline_cpi", "monthly_core_cpi", "mom_inflation_pct", "yoy_inflation_pct"]:
            if col in df_monthly_cpi.columns:
                df_monthly_cpi[col] = pd.to_numeric(df_monthly_cpi[col], errors="coerce")

    if df_nis_official is not None and not df_nis_official.empty:
        df_nis_official = df_nis_official.copy()
        for col in ["headline_cpi", "core_cpi", "mom_inflation_pct", "yoy_inflation_pct"]:
            if col in df_nis_official.columns:
                df_nis_official[col] = pd.to_numeric(df_nis_official[col], errors="coerce")

    # ── 1. Intra-Month Observed Dynamics ─────────────────────────────────────
    food_mom_signal = 0.0
    transport_mom_signal = 0.0

    if df_daily_cpi is None or df_daily_cpi.empty:
        realized_headline = 100.0
        realized_core = 100.0
        div_means = {d: 100.0 for d in NIS_COICOP_WEIGHTS}
    else:
        month_mask = (
            (df_daily_cpi["calculation_date"] >= target_month_start)
            & (df_daily_cpi["calculation_date"] <= target_date)
        )
        curr_month_df = df_daily_cpi[month_mask]

        if curr_month_df.empty:
            realized_headline = 100.0
            realized_core = 100.0
            div_means = {d: 100.0 for d in NIS_COICOP_WEIGHTS}
        else:
            daily_headline = curr_month_df.groupby("calculation_date")["headline_cpi"].first()
            realized_headline = float(daily_headline.mean()) if not daily_headline.empty else 100.0
            daily_core = curr_month_df.groupby("calculation_date")["core_cpi"].first().dropna() if "core_cpi" in curr_month_df else None
            realized_core = float(daily_core.mean()) if daily_core is not None and not daily_core.empty else realized_headline

            div_means = {}
            for div_code in NIS_COICOP_WEIGHTS:
                sub = curr_month_df[curr_month_df["coicop_division"] == div_code]
                div_means[div_code] = float(sub["division_index"].mean()) if not sub.empty else 100.0

        # Dedicated Food (Div 01) and Transport (Div 07) Momentum Signals (>57% of NIS Basket)
        food_index = div_means.get("01", 100.0)
        transport_index = div_means.get("07", 100.0)
        food_mom_signal = float(((food_index - 100.0) / 100.0) * 100.0)
        transport_mom_signal = float(((transport_index - 100.0) / 100.0) * 100.0)

    # ── 2. Rolling Moving Averages & Volatility Across Recent Days ────────────
    unique_dates = sorted(df_daily_cpi["calculation_date"].unique()) if df_daily_cpi is not None and not df_daily_cpi.empty else []
    recent_dates = [d for d in unique_dates if d <= target_date]

    ma7_headline = realized_headline
    ma14_headline = realized_headline
    ma30_headline = realized_headline
    volatility14 = 0.0

    if recent_dates:
        daily_headline = (
            df_daily_cpi[df_daily_cpi["calculation_date"].isin(recent_dates)]
            .groupby("calculation_date")["headline_cpi"]
            .first()
            .astype(float)
            .sort_index()
        )

        n_pts = len(daily_headline)
        ma7_headline = float(daily_headline.tail(min(n_pts, FEATURE_WINDOWS["short_ma"])).mean())
        ma14_headline = float(daily_headline.tail(min(n_pts, FEATURE_WINDOWS["medium_ma"])).mean())
        ma30_headline = float(daily_headline.tail(min(n_pts, FEATURE_WINDOWS["long_ma"])).mean())

        if n_pts >= 2:
            vol_tail = daily_headline.tail(min(n_pts, FEATURE_WINDOWS["volatility_window"]))
            volatility14 = float(vol_tail.pct_change().dropna().std())
            if np.isnan(volatility14):
                volatility14 = 0.0

    # ── 3. High-Frequency Exchange Rate Dynamics ─────────────────────────────
    fx_rate_today = 4044.0
    fx_change_7d_pct = 0.0

    if df_exchange_rates is not None and not df_exchange_rates.empty:
        rates_sorted = df_exchange_rates.sort_values("execution_date")
        prior_fx = rates_sorted[rates_sorted["execution_date"] <= target_date]
        if not prior_fx.empty:
            fx_rate_today = float(prior_fx.iloc[-1]["rate"])
            if len(prior_fx) >= 7:
                rate_7d_ago = float(prior_fx.iloc[-7]["rate"])
                if rate_7d_ago > 0:
                    fx_change_7d_pct = float(((fx_rate_today - rate_7d_ago) / rate_7d_ago) * 100.0)

    # ── 4. Lagged Monthly Ground Truth Inflation & NIS Anchors ────────────────
    prior_month_cpi = 100.0
    lag1_mom_inflation = 0.0

    if df_monthly_cpi is not None and not df_monthly_cpi.empty:
        m_sorted = df_monthly_cpi[df_monthly_cpi["cpi_month"] < target_month_start].sort_values("cpi_month")
        if not m_sorted.empty:
            prior_val = m_sorted.iloc[-1].get("monthly_headline_cpi")
            prior_month_cpi = float(prior_val) if pd.notna(prior_val) else 100.0
            
            mom_val = m_sorted.iloc[-1].get("mom_inflation_pct")
            lag1_mom_inflation = float(mom_val) if pd.notna(mom_val) else 0.0

    # Extract official NIS benchmarks if available from database (gold.dim_nis_official_cpi)
    latest_nis_cpi = 100.0
    latest_nis_core_cpi = 100.0
    latest_nis_month = target_month_start - timedelta(days=30)

    if df_nis_official is not None and not df_nis_official.empty:
        nis_sorted = df_nis_official[df_nis_official["cpi_month"] < target_month_start].sort_values("cpi_month")
        if not nis_sorted.empty:
            last_nis_row = nis_sorted.iloc[-1]
            nis_head_val = last_nis_row.get("headline_cpi")
            if pd.notna(nis_head_val):
                latest_nis_cpi = float(nis_head_val)
            
            nis_core_val = last_nis_row.get("core_cpi")
            if pd.notna(nis_core_val):
                latest_nis_core_cpi = float(nis_core_val)
            
            latest_nis_month = last_nis_row.get("cpi_month", latest_nis_month)

            # Check if official lag should supplement or override
            if lag1_mom_inflation == 0.0:
                nis_mom_val = last_nis_row.get("mom_inflation_pct")
                if pd.notna(nis_mom_val):
                    lag1_mom_inflation = float(nis_mom_val)

    # ── 5. Holiday & Calendar Indicators ─────────────────────────────────────
    holiday_dict = get_holiday_features(target_date)

    return {
        "target_date": target_date,
        "target_month": target_month_start,
        "days_observed": days_observed,
        "days_remaining": days_remaining,
        "days_in_month": total_days_in_month,
        "observed_ratio": observed_ratio,
        "realized_headline_cpi": realized_headline,
        "realized_core_cpi": realized_core,
        "food_div_index": div_means.get("01", 100.0),
        "housing_div_index": div_means.get("04", 100.0),
        "transport_div_index": div_means.get("07", 100.0),
        "food_mom_signal": food_mom_signal,
        "transport_mom_signal": transport_mom_signal,
        "ma7_headline": ma7_headline,
        "ma14_headline": ma14_headline,
        "ma30_headline": ma30_headline,
        "volatility14": volatility14,
        "fx_rate_today": fx_rate_today,
        "fx_change_7d_pct": fx_change_7d_pct,
        "prior_month_cpi": prior_month_cpi,
        "lag1_mom_inflation": lag1_mom_inflation,
        "latest_nis_cpi": latest_nis_cpi,
        "latest_nis_core_cpi": latest_nis_core_cpi,
        "latest_nis_month": latest_nis_month,
        **holiday_dict,
    }


