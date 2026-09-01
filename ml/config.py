"""
ml/config.py
────────────
Configuration parameters, official NIS expenditure weights, Cambodian holiday calendars,
and feature engineering definitions for Inflation Nowcasting and Forecasting.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Official NIS Cambodia 12 COICOP Division Weights
NIS_COICOP_WEIGHTS: dict[str, dict[str, Any]] = {
    "01": {"name": "Food and non-alcoholic beverages", "weight": 0.44800},
    "02": {"name": "Alcoholic beverages, tobacco and narcotics", "weight": 0.01500},
    "03": {"name": "Clothing and footwear", "weight": 0.02900},
    "04": {"name": "Housing, water, electricity, gas and other fuels", "weight": 0.17100},
    "05": {"name": "Furnishings, household equipment and routine household maintenance", "weight": 0.03300},
    "06": {"name": "Health", "weight": 0.05600},
    "07": {"name": "Transport", "weight": 0.12200},
    "08": {"name": "Communication", "weight": 0.03900},
    "09": {"name": "Recreation and culture", "weight": 0.01900},
    "10": {"name": "Education", "weight": 0.01500},
    "11": {"name": "Restaurants and hotels", "weight": 0.03100},
    "12": {"name": "Miscellaneous goods and services", "weight": 0.02200},
}

# Major Cambodian Cultural & National Holidays (Month, Day) for seasonal spike detection
CAMBODIA_ANNUAL_HOLIDAYS = [
    {"name": "Khmer New Year", "month": 4, "peak_days": [13, 14, 15, 16], "window_days": 4},
    {"name": "Pchum Ben", "month": 9, "peak_days": [28, 29, 30], "window_days": 5},
    {"name": "Pchum Ben (Alt/Oct)", "month": 10, "peak_days": [1, 2, 3], "window_days": 4},
    {"name": "Water Festival (Bon Om Touk)", "month": 11, "peak_days": [14, 15, 16], "window_days": 4},
    {"name": "Independence Day", "month": 11, "peak_days": [9], "window_days": 1},
    {"name": "International New Year", "month": 1, "peak_days": [1], "window_days": 2},
]

# Rolling window parameters for nowcasting features
FEATURE_WINDOWS = {
    "short_ma": 7,
    "medium_ma": 14,
    "long_ma": 30,
    "volatility_window": 14,
}

# Default Confidence Interval settings
CI_ALPHA = 0.05  # 95% Confidence Interval (z = 1.96)
Z_SCORE_95 = 1.95996
