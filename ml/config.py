"""
ml/config.py
────────────
Configuration parameters, official NIS expenditure weights, Cambodian holiday calendars,
and analytical definitions for Real-Time Inflation Nowcasting.
"""

from __future__ import annotations

from typing import Any

# Official NIS Cambodia 12 COICOP Division Weights (Phnom Penh CSES Oct-Dec 2006 = 100)
NIS_COICOP_WEIGHTS: dict[str, dict[str, Any]] = {
    "01": {"name": "Food and non-alcoholic beverages", "weight": 0.44775},
    "02": {"name": "Alcoholic beverages, tobacco and narcotics", "weight": 0.01625},
    "03": {"name": "Clothing and footwear", "weight": 0.03036},
    "04": {"name": "Housing, water, electricity, gas and other fuels", "weight": 0.17084},
    "05": {"name": "Furnishings, household equipment and routine household maintenance", "weight": 0.03250},
    "06": {"name": "Health", "weight": 0.05560},
    "07": {"name": "Transport", "weight": 0.12180},
    "08": {"name": "Communication", "weight": 0.03920},
    "09": {"name": "Recreation and culture", "weight": 0.01910},
    "10": {"name": "Education", "weight": 0.01510},
    "11": {"name": "Restaurants and hotels", "weight": 0.03085},
    "12": {"name": "Miscellaneous goods and services", "weight": 0.02065},
}

# Major Cambodian Cultural & National Holidays for seasonal spike detection.
# Fixed solar holidays + Year-specific Khmer Buddhist Lunar Calendar dates (Pchum Ben, Water Festival)
# Official Royal Government of Cambodia annual public holiday sub-decrees:
# - 2024: Pchum Ben Oct 1-3, Water Festival Nov 14-16
# - 2025: Pchum Ben Sep 21-23, Water Festival Nov 4-6
# - 2026: Pchum Ben Oct 10-12, Water Festival Nov 23-25
# - 2027: Pchum Ben Sep 29-Oct 1, Water Festival Nov 12-14
CAMBODIA_LUNAR_HOLIDAYS_BY_YEAR: dict[int, list[dict[str, Any]]] = {
    2024: [
        {"name": "Pchum Ben", "month": 10, "peak_days": [1, 2, 3], "window_days": 5},
        {"name": "Water Festival (Bon Om Touk)", "month": 11, "peak_days": [14, 15, 16], "window_days": 4},
    ],
    2025: [
        {"name": "Pchum Ben", "month": 9, "peak_days": [21, 22, 23], "window_days": 5},
        {"name": "Water Festival (Bon Om Touk)", "month": 11, "peak_days": [4, 5, 6], "window_days": 4},
    ],
    2026: [
        {"name": "Pchum Ben", "month": 10, "peak_days": [10, 11, 12], "window_days": 5},
        {"name": "Water Festival (Bon Om Touk)", "month": 11, "peak_days": [23, 24, 25], "window_days": 4},
    ],
    2027: [
        {"name": "Pchum Ben", "month": 9, "peak_days": [29, 30], "window_days": 5},
        {"name": "Pchum Ben Day 3", "month": 10, "peak_days": [1], "window_days": 5},
        {"name": "Water Festival (Bon Om Touk)", "month": 11, "peak_days": [12, 13, 14], "window_days": 4},
    ],
}

# Solar/Fixed Annual Holidays
CAMBODIA_FIXED_HOLIDAYS: list[dict[str, Any]] = [
    {"name": "International New Year", "month": 1, "peak_days": [1], "window_days": 2},
    {"name": "Victory over Genocide Day", "month": 1, "peak_days": [7], "window_days": 1},
    {"name": "International Women's Day", "month": 3, "peak_days": [8], "window_days": 1},
    {"name": "Khmer New Year", "month": 4, "peak_days": [13, 14, 15, 16], "window_days": 4},
    {"name": "International Labor Day", "month": 5, "peak_days": [1], "window_days": 1},
    {"name": "King Norodom Sihamoni Birthday", "month": 5, "peak_days": [14], "window_days": 1},
    {"name": "National Day of Remembrance", "month": 5, "peak_days": [20], "window_days": 1},
    {"name": "Queen Mother Birthday", "month": 6, "peak_days": [18], "window_days": 1},
    {"name": "Constitutional Day", "month": 9, "peak_days": [24], "window_days": 1},
    {"name": "Commemoration of Former King Father", "month": 10, "peak_days": [15], "window_days": 1},
    {"name": "Independence Day", "month": 11, "peak_days": [9], "window_days": 1},
]

def get_cambodia_holidays_for_year(year: int) -> list[dict[str, Any]]:
    """Returns combined fixed and lunar holidays for a given calendar year."""
    lunar = CAMBODIA_LUNAR_HOLIDAYS_BY_YEAR.get(year)
    if lunar is None:
        # Fallback approximation if year is not explicitly mapped
        lunar = [
            {"name": "Pchum Ben (Estimated)", "month": 10, "peak_days": [1, 2, 3], "window_days": 5},
            {"name": "Water Festival (Estimated)", "month": 11, "peak_days": [15, 16, 17], "window_days": 4},
        ]
    return list(CAMBODIA_FIXED_HOLIDAYS) + lunar

# Default fallback list for backwards compatibility
CAMBODIA_ANNUAL_HOLIDAYS = get_cambodia_holidays_for_year(2026)

# Rolling window parameters for time-series features
FEATURE_WINDOWS = {
    "short_ma": 7,
    "medium_ma": 14,
    "long_ma": 30,
    "volatility_window": 14,
}

# Default Confidence Interval settings
CI_ALPHA = 0.05  # 95% Confidence Interval (z = 1.96)
Z_SCORE_95 = 1.95996

# 5 Key Market-Driven Nowcasting Baskets (representing ~81.6% of Cambodia's CPI)
NOWCAST_TARGET_BASKETS: list[str] = ["01", "02", "04", "07", "11"]

BASKET_COLUMN_MAP: dict[str, str] = {
    "01": "food",
    "02": "alcohol",
    "04": "housing",
    "07": "transport",
    "11": "restaurant",
}

DEFAULT_NOWCAST_MODEL: str = "hybrid_ridge_5basket_v1"

# Ridge Regression hyperparameter search grid for Generalized Cross-Validation (RidgeCV)
RIDGE_ALPHAS: list[float] = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0]

