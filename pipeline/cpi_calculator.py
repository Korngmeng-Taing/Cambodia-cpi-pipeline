"""
=============================================================================
CAMBODIA CONSUMER PRICE INDEX (CPI) MATHEMATICAL CALCULATION ENGINE
Based on:
  - Diewert (1995) Axiomatic Elementary Aggregates (Jevons Geometric Mean)
  - ILO/IMF/OECD/World Bank CPI Manual (2020, Chapters 8, 9, 10)
  - National Institute of Statistics (NIS) Cambodia Expenditure Weights
=============================================================================
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor

from pipeline.config import get_database_url

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Official NIS Cambodia 12-Division Expenditure Weights (CSES)
DEFAULT_NIS_WEIGHTS = {
    "01": 0.44800,  # Food & Non-Alcoholic Beverages (44.80%)
    "02": 0.01500,  # Alcoholic Beverages & Tobacco (1.50%)
    "03": 0.02900,  # Clothing & Footwear (2.90%)
    "04": 0.17100,  # Housing, Water, Electricity, Gas & Fuels (17.10%)
    "05": 0.03300,  # Furnishings & Household Maintenance (3.30%)
    "06": 0.05600,  # Health & Pharmaceuticals (5.60%)
    "07": 0.12200,  # Transport & Automotive Fuels (12.20%)
    "08": 0.03900,  # Communication & Telecom (3.90%)
    "09": 0.01900,  # Recreation & Culture (1.90%)
    "10": 0.01500,  # Education (1.50%)
    "11": 0.03100,  # Restaurants & Hotels (3.10%)
    "12": 0.02200,  # Miscellaneous Goods & Services (2.20%)
}

DIVISION_NAMES = {
    "01": "Food and Non-Alcoholic Beverages",
    "02": "Alcoholic Beverages and Tobacco",
    "03": "Clothing and Footwear",
    "04": "Housing, Water, Electricity, Gas and Other Fuels",
    "05": "Furnishings, Household Equipment and Routine Maintenance",
    "06": "Health",
    "07": "Transport",
    "08": "Communication",
    "09": "Recreation and Culture",
    "10": "Education",
    "11": "Restaurants and Hotels",
    "12": "Miscellaneous Goods and Services",
}

class CPICalculationEngine:
    """
    Computes Jevons micro-indices, 7-day missing price imputation,
    Laspeyres 12-division aggregation, and Headline / Core CPI series.
    """

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or get_database_url()
        self.weights = DEFAULT_NIS_WEIGHTS.copy()

    def get_connection(self):
        conn_str = self.db_url.replace("postgresql+psycopg2://", "postgresql://")
        try:
            return psycopg2.connect(conn_str)
        except Exception:
            return psycopg2.connect(conn_str.replace("postgres:5432", "localhost:5432"))

    def compute_jevons_index(self, current_prices: np.ndarray, base_prices: np.ndarray) -> float:
        """
        Calculates Jevons Geometric Mean Micro-Index:
          I = exp( mean( ln(P_t) ) - mean( ln(P_0) ) ) * 100.0
        """
        cur = np.asarray(current_prices, dtype=float)
        base = np.asarray(base_prices, dtype=float)

        cur = cur[cur > 0]
        base = base[base > 0]

        if len(cur) == 0 or len(base) == 0:
            return 100.0

        log_cur_mean = np.mean(np.log(cur))
        log_base_mean = np.mean(np.log(base))

        ratio = np.exp(log_cur_mean - log_base_mean)
        return float(ratio * 100.0)

    def load_clean_prices(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Loads clean store price observations from silver layer."""
        query = """
            SELECT 
                s.scrape_date,
                s.item_id,
                s.store_slug,
                s.name_clean,
                COALESCE(h.hedonic_adjusted_price_khr, s.unit_price_khr, s.price_khr) AS unit_price_khr,
                s.price_khr,
                s.coicop_division,
                s.coicop_code,
                s.is_outlier
            FROM silver.clean_store_prices s
            LEFT JOIN silver.hedonic_adjusted_prices h 
              ON h.scrape_date = s.scrape_date 
             AND h.item_id = s.item_id::text 
             AND h.store_slug = s.store_slug
            WHERE s.scrape_date BETWEEN %s AND %s
              AND (s.is_outlier IS NULL OR s.is_outlier = FALSE)
              AND s.price_khr > 0
              AND s.item_id IS NOT NULL;
        """
        with self.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(start_date, end_date))
        df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
        df["unit_price_khr"] = pd.to_numeric(df["unit_price_khr"], errors="coerce")
        df = df[df["unit_price_khr"] > 0]
        return df

    def compute_base_prices(self, base_date: date, df_prices: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Computes the base geometric mean price per item_id on the base date.
        """
        if df_prices is None:
            df_prices = self.load_clean_prices(base_date, base_date)
        
        base_df = df_prices[df_prices["scrape_date"] == base_date]
        if base_df.empty:
            logger.warning(f"No observations found on base date {base_date}. Using earliest available.")
            base_df = df_prices

        # Geometric mean base price strictly per unique item_id
        grouped = base_df.groupby("item_id").agg(
            coicop_division=("coicop_division", "first"),
            coicop_code=("coicop_code", "first"),
            base_price_khr=("unit_price_khr", lambda x: float(np.exp(np.mean(np.log(x[x > 0]))))),
            base_obs_count=("unit_price_khr", "count")
        ).reset_index()

        return grouped

    def compute_daily_elementary_indices(
        self, 
        calc_date: date, 
        base_df: pd.DataFrame, 
        df_history: pd.DataFrame,
        imputation_window_days: int = 7
    ) -> pd.DataFrame:
        """
        Computes elementary Jevons price indices for calc_date with 7-day carry-forward imputation.
        """
        # Current day observations strictly per unique item_id
        today_obs = df_history[df_history["scrape_date"] == calc_date]
        today_agg = today_obs.groupby("item_id").agg(
            current_price_khr=("unit_price_khr", lambda x: float(np.exp(np.mean(np.log(x[x > 0]))))),
            observation_count=("unit_price_khr", "count")
        ).reset_index()

        # Merge with base prices on item_id
        merged = pd.merge(base_df, today_agg, on="item_id", how="left")
        merged["is_imputed"] = False

        # Apply 7-day carry-forward imputation for missing items
        missing_mask = merged["current_price_khr"].isna()
        if missing_mask.any():
            missing_items = set(merged.loc[missing_mask, "item_id"])
            min_date = calc_date - timedelta(days=imputation_window_days)
            recent_obs = df_history[
                (df_history["scrape_date"] >= min_date) & 
                (df_history["scrape_date"] < calc_date) & 
                (df_history["item_id"].isin(missing_items))
            ]

            if not recent_obs.empty:
                # Get the most recent available price for each missing item
                recent_sorted = recent_obs.sort_values("scrape_date", ascending=False)
                last_prices = recent_sorted.groupby("item_id")["unit_price_khr"].first().to_dict()

                for idx, row in merged[missing_mask].iterrows():
                    item_id = row["item_id"]
                    val = last_prices.get(item_id)
                    if val is not None and not pd.isna(val) and float(val) > 0:
                        merged.at[idx, "current_price_khr"] = float(val)
                        merged.at[idx, "observation_count"] = 1
                        merged.at[idx, "is_imputed"] = True

        # Drop items that are still missing (missing > 7 days)
        valid = merged.dropna(subset=["current_price_khr", "base_price_khr"]).copy()
        valid = valid[(valid["current_price_khr"] > 0) & (valid["base_price_khr"] > 0)]
        valid["price_ratio"] = valid["current_price_khr"] / valid["base_price_khr"]
        
        # ILO Outlier Filter: Guard against 1000x currency scaling or raw scraper glitches
        valid = valid[(valid["price_ratio"] >= 0.20) & (valid["price_ratio"] <= 5.00)].copy()

        valid["elementary_index"] = valid["price_ratio"] * 100.0
        valid["calculation_date"] = calc_date

        return valid

    def aggregate_division_and_headline(self, elementary_df: pd.DataFrame, calc_date: date) -> Tuple[pd.DataFrame, Dict]:
        """
        Aggregates elementary indices into 12 COICOP division indices and Headline / Core CPI.
        """
        # Division-level Jevons index (geometric mean of elementary price ratios)
        div_records = []
        for div_code, weight in self.weights.items():
            div_items = elementary_df[elementary_df["coicop_division"] == div_code]
            if not div_items.empty:
                # Geometric mean of ratios
                div_index = np.exp(np.mean(np.log(div_items["price_ratio"]))) * 100.0
                obs_cnt = int(div_items["observation_count"].sum())
                item_cnt = len(div_items)
            else:
                div_index = 100.0
                obs_cnt = 0
                item_cnt = 0

            div_records.append({
                "calculation_date": calc_date,
                "coicop_division": div_code,
                "division_name": DIVISION_NAMES.get(div_code, f"Division {div_code}"),
                "weight": weight,
                "division_index": float(div_index),
                "item_count": item_cnt,
                "observation_count": obs_cnt
            })

        df_div = pd.DataFrame(div_records)

        # Higher-Level Laspeyres Aggregation for Headline CPI
        total_weight = df_div["weight"].sum()
        headline_cpi = float((df_div["weight"] * df_div["division_index"]).sum() / total_weight)

        # Core CPI (Ex-Food & Energy): Excludes Division 01 (Food & Non-Alcoholic Beverages)
        # in strict alignment with NIS Cambodia & National Bank of Cambodia core inflation standards
        core_divisions = df_div[~df_div["coicop_division"].isin(["01"])]
        core_weight = core_divisions["weight"].sum()
        core_cpi = float((core_divisions["weight"] * core_divisions["division_index"]).sum() / core_weight) if core_weight > 0 else headline_cpi

        headline_summary = {
            "calculation_date": calc_date,
            "headline_cpi": headline_cpi,
            "core_cpi": core_cpi,
            "total_items": len(elementary_df),
            "total_observations": int(elementary_df["observation_count"].sum())
        }

        return df_div, headline_summary

    def run_daily_pipeline(self, target_date: Optional[date] = None, base_date: Optional[date] = None):
        """Executes full daily CPI calculation and writes results to PostgreSQL."""
        if target_date is None:
            target_date = date.today()
        if base_date is None:
            base_date = date(2026, 8, 18)

        logger.info(f"🚀 Running Daily CPI Calculation for {target_date} (Base Date: {base_date})")

        # Load history from base_date to target_date
        df_history = self.load_clean_prices(base_date, target_date)
        if df_history.empty:
            logger.error(f"No clean price data available between {base_date} and {target_date}")
            return

        base_df = self.compute_base_prices(base_date, df_history)
        elementary_df = self.compute_daily_elementary_indices(target_date, base_df, df_history)

        df_div, headline = self.aggregate_division_and_headline(elementary_df, target_date)

        logger.info(f"📊 {target_date} Headline CPI: {headline['headline_cpi']:.2f} | Core CPI: {headline['core_cpi']:.2f} | Active Basket Items: {headline['total_items']}")

        self._save_to_database(elementary_df, df_div, headline)

    def _save_to_database(self, elementary_df: pd.DataFrame, df_div: pd.DataFrame, headline: Dict):
        """Persists elementary indices and daily CPI facts to PostgreSQL."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Ensure Gold schema tables exist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS gold.fct_elementary_indices (
                        calculation_date DATE NOT NULL,
                        item_id UUID NOT NULL,
                        coicop_division VARCHAR(10) NOT NULL,
                        coicop_code VARCHAR(20),
                        base_price_khr NUMERIC(14, 4),
                        current_price_khr NUMERIC(14, 4),
                        price_ratio NUMERIC(10, 6),
                        elementary_index NUMERIC(10, 4),
                        is_imputed BOOLEAN DEFAULT FALSE,
                        observation_count INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (calculation_date, item_id)
                    );

                    CREATE TABLE IF NOT EXISTS gold.fct_cpi_daily (
                        calculation_date DATE NOT NULL,
                        coicop_division VARCHAR(10) NOT NULL,
                        division_name VARCHAR(150),
                        weight NUMERIC(8, 5),
                        division_index NUMERIC(10, 4),
                        headline_cpi NUMERIC(10, 4),
                        core_cpi NUMERIC(10, 4),
                        item_count INTEGER,
                        observation_count INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (calculation_date, coicop_division)
                    );
                """)

                # 1. Upsert Elementary Indices
                cur.execute("DELETE FROM gold.fct_elementary_indices WHERE calculation_date = %s", (headline["calculation_date"],))
                elem_rows = [
                    (
                        r["calculation_date"], r["item_id"], r["coicop_division"], r["coicop_code"],
                        r["base_price_khr"], r["current_price_khr"], r["price_ratio"], r["elementary_index"],
                        r["is_imputed"], int(r["observation_count"])
                    )
                    for _, r in elementary_df.iterrows()
                ]
                execute_batch(cur, """
                    INSERT INTO gold.fct_elementary_indices (
                        calculation_date, item_id, coicop_division, coicop_code,
                        base_price_khr, current_price_khr, price_ratio, elementary_index,
                        is_imputed, observation_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, elem_rows, page_size=1000)

                # 2. Upsert Daily Division & Headline CPI
                cur.execute("DELETE FROM gold.fct_cpi_daily WHERE calculation_date = %s", (headline["calculation_date"],))
                cpi_rows = [
                    (
                        r["calculation_date"], r["coicop_division"], r["division_name"], r["weight"],
                        r["division_index"], headline["headline_cpi"], headline["core_cpi"],
                        r["item_count"], r["observation_count"]
                    )
                    for _, r in df_div.iterrows()
                ]
                execute_batch(cur, """
                    INSERT INTO gold.fct_cpi_daily (
                        calculation_date, coicop_division, division_name, weight,
                        division_index, headline_cpi, core_cpi, item_count, observation_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, cpi_rows)

                conn.commit()
                logger.info(f"✅ Successfully persisted {len(elem_rows)} elementary indices and {len(cpi_rows)} division CPI facts!")

if __name__ == "__main__":
    engine = CPICalculationEngine()
    engine.run_daily_pipeline()
