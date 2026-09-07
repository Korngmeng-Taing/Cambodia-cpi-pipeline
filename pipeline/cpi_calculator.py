"""
=============================================================================
CAMBODIA CONSUMER PRICE INDEX (CPI) MATHEMATICAL CALCULATION ENGINE
Based on:
  - Diewert (1995) Axiomatic Elementary Aggregates (Jevons Geometric Mean)
  - ILO/IMF/OECD/World Bank CPI Manual (2020, Chapters 8, 9, 10)
  - National Institute of Statistics (NIS) Cambodia Expenditure Weights
=============================================================================
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

from pipeline.config import get_database_url

log = logging.getLogger(__name__)

# Official NIS Cambodia 12-Division Expenditure Weights (CSES Oct-Dec 2006 = 100)
DEFAULT_NIS_WEIGHTS = {
    "01": 0.44775,  # Food & Non-Alcoholic Beverages (44.775%)
    "02": 0.01625,  # Alcoholic Beverages & Tobacco (1.625%)
    "03": 0.03036,  # Clothing & Footwear (3.036%)
    "04": 0.17084,  # Housing, Water, Electricity, Gas & Fuels (17.084%)
    "05": 0.03250,  # Furnishings & Household Maintenance (3.250%)
    "06": 0.05560,  # Health & Pharmaceuticals (5.560%)
    "07": 0.12180,  # Transport & Automotive Fuels (12.180%)
    "08": 0.03920,  # Communication & Telecom (3.920%)
    "09": 0.01910,  # Recreation & Culture (1.910%)
    "10": 0.01510,  # Education (1.510%)
    "11": 0.03085,  # Restaurants & Hotels (3.085%)
    "12": 0.02065,  # Miscellaneous Goods & Services (2.065%)
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

# Official NIS Cambodia 4-Digit COICOP Subclass / Class Expenditure Weights (Base: Oct-Dec 2006 = 100)
# Matches dbt/seeds/cambodia_cpi_coicop_weights_breakdown.csv
DEFAULT_SUBCLASS_WEIGHTS = {
    "01.1.1": 17.230,  # Bread and cereals
    "01.1.2": 8.450,   # Meat
    "01.1.3": 7.120,   # Fish and seafood
    "01.1.4": 1.850,   # Milk, cheese and eggs
    "01.1.5": 1.140,   # Oils and fats
    "01.1.6": 2.460,   # Fruit
    "01.1.7": 2.380,   # Vegetables
    "01.1.8": 0.720,   # Sugar, jam, honey, chocolate
    "01.1.9": 0.630,   # Food products n.e.c.
    "01.2.1": 0.515,   # Coffee, tea and cocoa
    "01.2.2": 2.280,   # Mineral waters, soft drinks, juices
    "02.1.1": 0.210,   # Spirits and liqueurs
    "02.1.2": 0.085,   # Wine
    "02.1.3": 0.750,   # Beer
    "02.2.0": 0.580,   # Tobacco
    "03.1.2": 2.140,   # Garments
    "03.1.3": 0.146,   # Other articles of clothing & accessories
    "03.2.1": 0.750,   # Shoes and other footwear
    "04.1.1": 9.420,   # Actual rentals paid by tenants
    "04.3.1": 1.120,   # Materials for dwelling maintenance
    "04.4.1": 1.860,   # Water supply
    "04.5.1": 2.820,   # Electricity
    "04.5.2": 1.650,   # Gas
    "04.5.4": 0.214,   # Solid fuels
    "05.1.1": 0.820,   # Furniture and furnishings
    "05.2.1": 0.450,   # Household textiles
    "05.5.1": 0.380,   # Glassware, tableware, household utensils
    "05.6.1": 1.600,   # Non-durable household goods
    "06.1.1": 3.450,   # Pharmaceutical products
    "06.1.2": 0.370,   # Other medical products
    "06.2.1": 1.740,   # Medical services
    "07.1.2": 3.120,   # Motorcycles
    "07.2.2": 6.850,   # Fuels and lubricants
    "07.2.3": 0.560,   # Maintenance & repair of transport
    "07.3.2": 1.650,   # Passenger transport by bus, coach, van
    "08.2.0": 1.420,   # Telephone equipment
    "08.3.0": 2.500,   # Telephone and internet services
    "09.1.1": 0.620,   # Audio/visual reception & reproduction
    "09.1.3": 0.560,   # Information processing equipment
    "09.3.1": 0.420,   # Games, toys and hobbies
    "09.5.1": 0.310,   # Books and stationery
    "10.1.0": 1.510,   # Education services (tuition fees)
    "11.1.1": 2.435,   # Restaurants, cafes and the like
    "11.2.0": 0.650,   # Accommodation services
    "12.1.1": 0.405,   # Hairdressing & grooming
    "12.1.3": 0.930,   # Personal care appliances & products
    "12.3.1": 0.410,   # Jewellery, clocks and watches
    "12.3.2": 0.320,   # Other personal effects
}

class CPICalculationEngine:
    """
    Computes Jevons micro-indices, 7-day missing price imputation,
    subclass-weighted Laspeyres 12-division aggregation, and Headline / Core CPI series.
    """

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or get_database_url()
        self.weights = DEFAULT_NIS_WEIGHTS.copy()
        self.subclass_weights = self._load_subclass_weights()

    def _load_subclass_weights(self) -> dict[str, float]:
        """Loads official 4-digit / Class level COICOP expenditure weights from seed CSV or defaults."""
        weights = DEFAULT_SUBCLASS_WEIGHTS.copy()
        csv_path = Path(__file__).resolve().parent.parent / "dbt" / "seeds" / "cambodia_cpi_coicop_weights_breakdown.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path, dtype=str)
                df["weight_pct"] = pd.to_numeric(df["weight_pct"], errors="coerce")
                for _, row in df.iterrows():
                    code = str(row.get("coicop_code", "")).strip()
                    wt = row.get("weight_pct")
                    if code and not pd.isna(wt) and float(wt) > 0:
                        weights[code] = float(wt)
            except Exception as e:
                log.warning("Could not load subclass weights from seed CSV: %s", e)
        return weights

    def _get_subclass_code(self, raw_code: str | None, div_code: str) -> str:
        """Resolves raw COICOP code into an official subclass / class code matching weights."""
        if raw_code is None or pd.isna(raw_code):
            return f"{div_code}.unclassified"
        code = str(raw_code).strip()
        if not code:
            return f"{div_code}.unclassified"
        if code in self.subclass_weights:
            return code
        if len(code) >= 6 and code[:6] in self.subclass_weights:
            return code[:6]
        if len(code) >= 4 and code[:4] in self.subclass_weights:
            return code[:4]
        return code

    def get_connection(self):
        conn_str = self.db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        try:
            return psycopg2.connect(conn_str)
        except psycopg2.OperationalError as e:
            # Use the alternate host URL defined in config for proper parsing and fallback handling
            from pipeline.config import alternate_host_url
            alt_url = alternate_host_url(self.db_url)
            try:
                return psycopg2.connect(alt_url)
            except psycopg2.OperationalError as e2:
                raise psycopg2.OperationalError(
                    f"Both primary and alternate hosts failed. Primary: {e}. Alternate: {e2}"
                ) from e2


    def load_clean_prices(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Loads clean store price observations from silver layer.

        NOTE: This reads from silver.clean_store_prices (NOT gold.fct_daily_prices).
        The CPI engine requires:
          1. Item-level aggregation across stores (geometric mean per item_id)
          2. Hedonic-adjusted prices from silver.hedonic_adjusted_prices
          3. COICOP division/code from the classification pipeline
        fct_daily_prices is at (scrape_date, store_slug, item_id) grain for BI/star schema
        and does not include hedonic adjustments or COICOP attribution.
        """
        query = """
            SELECT 
                s.scrape_date,
                s.item_id,
                s.store_slug,
                s.name_clean,
                COALESCE(h.hedonic_adjusted_price_khr, s.unit_price_khr, s.price_khr) AS unit_price_khr,
                s.price_khr,
                s.coicop_division,  -- post-classification division from clean_store_prices, NOT h.coicop_division
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
        # BUG FIX: psycopg2 context manager only manages transactions
        # (commit/rollback), NOT connection lifecycle. Must close explicitly.
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (start_date, end_date))
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=cols)
        finally:
            conn.close()
        df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
        df["unit_price_khr"] = pd.to_numeric(df["unit_price_khr"], errors="coerce")
        df = df[df["unit_price_khr"] > 0]
        return df

    def compute_jevons_index(self, current_prices, base_prices) -> float:
        """
        Diewert (1995) Jevons geometric-mean elementary price index.

        Returns the unweighted geometric-mean price ratio of ``current_prices``
        relative to ``base_prices``, expressed on a 100-base scale. Both inputs
        may be any array-like (list, tuple, numpy array); non-positive entries
        are filtered out. Returns 100.0 (the no-change neutral index) when no
        usable pairs remain.

        NOTE: Arrays must be pre-aligned (same item in the same position).
        If lengths differ a warning is emitted and the shorter length is used;
        callers should ensure alignment before invoking this method.
        """
        cur = np.asarray(current_prices, dtype=float)
        base = np.asarray(base_prices, dtype=float)
        if len(cur) == 0 or len(base) == 0:
            return 100.0
        if len(cur) != len(base):
            raise ValueError(
                f"compute_jevons_index: current_prices length ({len(cur)}) != base_prices length ({len(base)}). "
                "Arrays must be aligned by item_id before computing index."
            )
        valid_mask = (cur > 0) & (base > 0)
        cur = cur[valid_mask]
        base = base[valid_mask]
        if len(cur) == 0:
            return 100.0
        ratios = cur / base
        return float(np.exp(np.mean(np.log(ratios))) * 100.0)

    def compute_base_prices(self, base_date: date, df_prices: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        Computes the base geometric mean price per item_id on the base date.
        """
        if df_prices is None:
            df_prices = self.load_clean_prices(base_date, base_date)
        
        if df_prices.empty:
            log.warning("No price history available to compute base prices.")
            return pd.DataFrame(columns=["item_id", "coicop_division", "coicop_code", "base_price_khr", "base_obs_count"])

        base_df = df_prices[df_prices["scrape_date"] == base_date]
        if base_df.empty:
            log.warning(f"No observations found on base date {base_date}. Using earliest available.")
            earliest = df_prices["scrape_date"].min()
            base_df = df_prices[df_prices["scrape_date"] == earliest]

        if base_df.empty:
            return pd.DataFrame(columns=["item_id", "coicop_division", "coicop_code", "base_price_khr", "base_obs_count"])

        def _safe_geom_mean(x):
            valid = x[x > 0]
            if len(valid) == 0:
                return np.nan
            return float(np.exp(np.mean(np.log(valid))))

        # Geometric mean base price strictly per unique item_id
        grouped = base_df.groupby("item_id").agg(
            coicop_division=("coicop_division", "first"),
            coicop_code=("coicop_code", "first"),
            base_price_khr=("unit_price_khr", _safe_geom_mean),
            base_obs_count=("unit_price_khr", "count")
        ).reset_index()

        return grouped[grouped["base_price_khr"] > 0]

    def compute_daily_elementary_indices(
        self, 
        calc_date: date, 
        base_df: pd.DataFrame, 
        df_history: pd.DataFrame,
        imputation_window_days: int = 7
    ) -> pd.DataFrame:
        """
        Computes elementary Jevons price indices for calc_date with ILO Class-Mean Imputation.
        When an item is missing on day t (gap <= 7 days), its price is advanced using the
        geometric average rate of change of observed items in the same COICOP division.
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

        # Compute division movement ratios for observed items between yesterday and today
        prior_dates = sorted([d for d in df_history["scrape_date"].unique() if d < calc_date])
        prev_date = prior_dates[-1] if prior_dates else None
        
        division_movement_ratios: dict[str, float] = {}
        if prev_date is not None and not today_obs.empty:
            prev_obs = df_history[df_history["scrape_date"] == prev_date]
            prev_agg = prev_obs.groupby("item_id")["unit_price_khr"].agg(
                lambda x: float(np.exp(np.mean(np.log(x[x > 0]))))
            ).reset_index()
            
            # Common items between yesterday and today
            common = pd.merge(today_agg, prev_agg, on="item_id", suffixes=("_today", "_prev"))
            if not common.empty:
                common = pd.merge(common, base_df[["item_id", "coicop_division"]], on="item_id", how="left")
                common["ratio"] = common["current_price_khr"] / common["unit_price_khr"]
                common = common[(common["ratio"] >= 0.5) & (common["ratio"] <= 2.0)]
                for div, group in common.groupby("coicop_division"):
                    if len(group) > 0:
                        division_movement_ratios[str(div)] = float(np.exp(np.mean(np.log(group["ratio"]))))

        # Apply ILO Class-Mean Imputation for missing items (gap <= 7 days)
        missing_mask = merged["current_price_khr"].isna()
        if missing_mask.any():
            missing_items = set(merged.loc[missing_mask, "item_id"])
            if prev_date is not None:
                min_date = prev_date - timedelta(days=imputation_window_days)
            else:
                min_date = calc_date - timedelta(days=imputation_window_days)
            recent_obs = df_history[
                (df_history["scrape_date"] >= min_date) & 
                (df_history["scrape_date"] < calc_date) & 
                (df_history["item_id"].isin(missing_items))
            ]

            if not recent_obs.empty:
                # Find the most recent active scrape date for each missing item
                latest_dates = recent_obs.groupby("item_id")["scrape_date"].max().reset_index()
                latest_dates_dict = dict(zip(latest_dates["item_id"], latest_dates["scrape_date"]))
                latest_obs = pd.merge(
                    recent_obs, latest_dates, on=["item_id", "scrape_date"], how="inner"
                )
                # Compute geometric mean across stores on that latest date (Jevons elementary aggregation)
                last_prices = latest_obs.groupby("item_id")["unit_price_khr"].agg(
                    lambda x: float(np.exp(np.mean(np.log(x[x > 0])))) if len(x[x > 0]) > 0 else np.nan
                ).to_dict()

                for idx, row in merged[missing_mask].iterrows():
                    item_id = row["item_id"]
                    val = last_prices.get(item_id)
                    if val is not None and not pd.isna(val) and float(val) > 0:
                        div = str(row.get("coicop_division", "01"))
                        # Apply class-mean movement ratio if available, clamped to [0.80, 1.25]
                        movement = division_movement_ratios.get(div, 1.0)
                        movement = max(0.80, min(1.25, movement))
                        # BUG-01 FIX: Compound the 1-day movement ratio by the
                        # actual number of gap days between the last observation
                        # and calc_date.  Previously a single-day ratio was applied
                        # regardless of how stale the price was.
                        last_obs_date = latest_dates_dict.get(item_id)
                        if last_obs_date is not None:
                            days_gap = (pd.to_datetime(calc_date) - pd.to_datetime(last_obs_date)).days
                            days_gap = max(1, min(days_gap, 7))
                        else:
                            days_gap = 1
                        imputed_price = float(val) * (movement ** days_gap)
                        merged.at[idx, "current_price_khr"] = imputed_price
                        merged.at[idx, "observation_count"] = 1
                        merged.at[idx, "is_imputed"] = True

        # Drop items that are still missing (missing > 7 days)
        valid = merged.dropna(subset=["current_price_khr", "base_price_khr"]).copy()
        valid = valid[(valid["current_price_khr"] > 0) & (valid["base_price_khr"] > 0)]
        valid["price_ratio"] = valid["current_price_khr"] / valid["base_price_khr"]
        
        # ILO Outlier Filter: Guard against extreme price scaling or raw scraper glitches
        valid = valid[(valid["price_ratio"] >= 0.20) & (valid["price_ratio"] <= 5.00)].copy()

        # Store price ratio as a percentage (per-item Jevons index)
        valid["price_ratio_pct"] = valid["price_ratio"] * 100.0
        valid["calculation_date"] = calc_date

        return valid

    def aggregate_division_and_headline(
        self, 
        elementary_df: pd.DataFrame, 
        calc_date: date,
        splice_factor: float = 1.0
    ) -> tuple[pd.DataFrame, dict]:
        """
        Aggregates elementary indices into 12 COICOP division indices and Headline / Core CPI.
        Implements ILO/IMF two-tier aggregation:
          Tier 1: Jevons unweighted geometric mean of price ratios within each 4-digit COICOP subclass.
          Tier 2: Laspeyres expenditure-weighted aggregation of subclass indices to form division index.
          Tier 3: Laspeyres expenditure-weighted aggregation of division indices to form Headline / Core CPI.
        Optional splice_factor applies continuous series chain-linking on rebasing.
        """
        div_records = []
        has_coicop_code = "coicop_code" in elementary_df.columns

        for div_code, weight in self.weights.items():
            div_items = elementary_df[elementary_df["coicop_division"] == div_code]
            if not div_items.empty:
                # Group items by subclass within the division
                if has_coicop_code and div_items["coicop_code"].notna().any():
                    subclass_indices = []
                    subclass_wts = []

                    div_items_with_sub = div_items.copy()
                    div_items_with_sub["subclass_code"] = div_items_with_sub["coicop_code"].apply(
                        lambda c: self._get_subclass_code(c, div_code)
                    )

                    for sub_code, sub_group in div_items_with_sub.groupby("subclass_code"):
                        ratios = sub_group["price_ratio"][sub_group["price_ratio"] > 0]
                        if len(ratios) > 0:
                            sub_index = float(np.exp(np.mean(np.log(ratios))) * 100.0)
                            sub_wt = self.subclass_weights.get(sub_code)
                            subclass_indices.append(sub_index)
                            subclass_wts.append(sub_wt)

                    valid_wts = [w for w in subclass_wts if w is not None and w > 0]
                    if len(valid_wts) == len(subclass_wts) and sum(valid_wts) > 0:
                        div_index = sum(idx * wt for idx, wt in zip(subclass_indices, subclass_wts)) / sum(subclass_wts)
                    else:
                        # Fallback if subclass weights are missing: unweighted geometric mean across all division items
                        div_index = float(np.exp(np.mean(np.log(div_items["price_ratio"]))) * 100.0)
                else:
                    # No subclass codes provided: unweighted geometric mean across division items
                    div_index = float(np.exp(np.mean(np.log(div_items["price_ratio"]))) * 100.0)

                # Apply continuous chain-linking splice factor if applicable
                if splice_factor != 1.0 and not np.isnan(div_index):
                    div_index = div_index * splice_factor

                obs_cnt = int(div_items["observation_count"].sum())
                item_cnt = len(div_items)
            else:
                # FIX: Do NOT default to 100.0 — that artificially drags the
                # headline CPI toward 100 on days when a division is missing.
                # Instead, mark as NaN so its weight is excluded from the
                # Laspeyres aggregation denominator below.
                div_index = np.nan
                obs_cnt = 0
                item_cnt = 0
                log.info("Division %s (%s) has no items on %s — reweighting headline aggregation.",
                         div_code, DIVISION_NAMES.get(div_code, ""), elementary_df["calculation_date"].iloc[0] if not elementary_df.empty else "?")

            div_records.append({
                "calculation_date": calc_date,
                "coicop_division": div_code,
                "division_name": DIVISION_NAMES.get(div_code, f"Division {div_code}"),
                "weight": weight,
                "division_index": float(div_index) if not np.isnan(div_index) else None,
                "item_count": item_cnt,
                "observation_count": obs_cnt
            })

        df_div = pd.DataFrame(div_records)

        # Higher-Level Laspeyres Aggregation for Headline CPI
        # Only include divisions that actually have observed items;
        # exclude missing divisions from both numerator and denominator.
        active_div = df_div[df_div["item_count"] > 0]
        if active_div.empty:
            headline_cpi = 100.0 * splice_factor
        else:
            total_weight = active_div["weight"].sum()
            headline_cpi = float((active_div["weight"] * active_div["division_index"]).sum() / total_weight)

        # Core CPI (Ex-Food & Energy): Excludes Division 01 (Food & Non-Alcoholic Beverages),
        # Division 04 (Housing, Water, Electricity, Gas & Fuels), and Division 07 (Transport
        # & Automotive Fuels) — in alignment with NIS Cambodia & National Bank of Cambodia
        # core inflation standards and the project README.
        core_exclusions = {"01", "04", "07"}
        core_divisions = active_div[~active_div["coicop_division"].isin(core_exclusions)]
        core_weight = core_divisions["weight"].sum()
        # Renormalise the denominator to the sum of the CORE weights only. Using
        # the full 12-division total_weight here caused core_cpi to collapse to
        # ~25.9 on a base-period day (the sum of core weights) instead of 100.0.
        # See audit C1.
        core_cpi = float((core_divisions["weight"] * core_divisions["division_index"]).sum() / core_weight) if core_weight > 0 else headline_cpi

        headline_summary = {
            "calculation_date": calc_date,
            "headline_cpi": headline_cpi,
            "core_cpi": core_cpi,
            "total_items": len(elementary_df),
            "total_observations": int(elementary_df["observation_count"].sum())
        }

        return df_div, headline_summary

    def run_daily_pipeline(
        self, 
        target_date: date | None = None, 
        base_date: date | None = None,
        splice_factor: float | None = None
    ):
        """Executes full daily CPI calculation and writes results to PostgreSQL."""
        if target_date is None:
            target_date = date.today()

        log.info(f"🚀 Running Daily CPI Calculation for {target_date} (Base Date: {base_date})")

        # When base_date is unset, infer it as the earliest scrape_date with data.
        if base_date is None:
            conn = self.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT MIN(scrape_date) 
                        FROM silver.clean_store_prices 
                        WHERE price_khr > 0 AND item_id IS NOT NULL;
                    """)
                    row = cur.fetchone()
                    base_date = row[0] if row and row[0] else None
            finally:
                conn.close()

            if base_date is None:
                log.error("No price history available in silver.clean_store_prices to infer base_date.")
                return

            log.info(f"🔧 No base_date provided; using earliest available date {base_date} as base period.")

        # Load base period observations separately to compute base prices
        df_base = self.load_clean_prices(base_date, base_date)
        if df_base.empty:
            log.error(f"No clean price data available for base date {base_date}")
            return
        base_df = self.compute_base_prices(base_date, df_base)

        # Only load the trailing imputation window (target_date - 9 days to target_date)
        history_start = target_date - timedelta(days=9)
        df_history = self.load_clean_prices(history_start, target_date)

        if df_history.empty:
            log.error(f"No clean price data available between {history_start} and {target_date}")
            return

        elementary_df = self.compute_daily_elementary_indices(target_date, base_df, df_history)

        # Lookup continuous series chain-linking splice factor if not explicitly passed
        if splice_factor is None:
            splice_factor = 1.0
            try:
                conn = self.get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT avg_december_cpi 
                            FROM gold.cpi_base_dates 
                            WHERE effective_from <= %s 
                            ORDER BY effective_from DESC 
                            LIMIT 1;
                        """, (target_date,))
                        row = cur.fetchone()
                        if row and row[0] is not None and float(row[0]) > 0:
                            splice_factor = float(row[0]) / 100.0
                            log.info("Applying chain-linking splice factor: %.4f (avg_december_cpi=%.2f)", splice_factor, float(row[0]))
                finally:
                    conn.close()
            except Exception as e:
                log.debug("Could not query gold.cpi_base_dates for splice factor: %s. Defaulting to 1.0", e)

        df_div, headline = self.aggregate_division_and_headline(elementary_df, target_date, splice_factor=splice_factor)

        log.info(f"📊 {target_date} Headline CPI: {headline['headline_cpi']:.2f} | Core CPI: {headline['core_cpi']:.2f} | Active Basket Items: {headline['total_items']}")

        self._save_to_database(elementary_df, df_div, headline)

    def _save_to_database(self, elementary_df: pd.DataFrame, df_div: pd.DataFrame, headline: dict):
        """Persists elementary indices and daily CPI facts to PostgreSQL."""
        conn = self.get_connection()
        try:
          with conn.cursor() as cur:
                # Ensure Gold schema tables exist
                cur.execute("""
                     CREATE TABLE IF NOT EXISTS gold.fct_elementary_indices (
                         calculation_date DATE NOT NULL,
                         item_id TEXT NOT NULL,
                         coicop_division VARCHAR(10) NOT NULL,
                         coicop_code VARCHAR(20),
                         base_price_khr NUMERIC(14, 4),
                         current_price_khr NUMERIC(14, 4),
                         price_ratio NUMERIC(10, 6),
                         price_ratio_pct NUMERIC(10, 4),
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

                # Ensure price_ratio_pct column exists (table may have been created before this column was added)
                cur.execute("""
                    DO $$ BEGIN
                        ALTER TABLE gold.fct_elementary_indices ADD COLUMN IF NOT EXISTS price_ratio_pct NUMERIC(10, 4);
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                """)

                # 1. Upsert Elementary Indices
                elem_rows = [
                    (
                        r["calculation_date"], str(r["item_id"]), r["coicop_division"], r["coicop_code"],
                        r["base_price_khr"], r["current_price_khr"], r["price_ratio"], r["price_ratio_pct"],
                        r["is_imputed"], int(r["observation_count"])
                    )
                    for _, r in elementary_df.iterrows()
                ]
                execute_batch(cur, """
                    INSERT INTO gold.fct_elementary_indices (
                        calculation_date, item_id, coicop_division, coicop_code,
                        base_price_khr, current_price_khr, price_ratio, price_ratio_pct,
                        is_imputed, observation_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (calculation_date, item_id) DO UPDATE
                    SET coicop_division = EXCLUDED.coicop_division,
                        coicop_code = EXCLUDED.coicop_code,
                        base_price_khr = EXCLUDED.base_price_khr,
                        current_price_khr = EXCLUDED.current_price_khr,
                        price_ratio = EXCLUDED.price_ratio,
                        price_ratio_pct = EXCLUDED.price_ratio_pct,
                        is_imputed = EXCLUDED.is_imputed,
                        observation_count = EXCLUDED.observation_count
                """, elem_rows, page_size=1000)

                # 2. Upsert Daily Division & Headline CPI
                cpi_rows = [
                    (
                        r["calculation_date"], r["coicop_division"], r["division_name"], r["weight"],
                        None if pd.isna(r["division_index"]) else float(r["division_index"]),
                        headline["headline_cpi"], headline["core_cpi"],
                        int(r["item_count"]), int(r["observation_count"])
                    )
                    for _, r in df_div.iterrows()
                ]
                execute_batch(cur, """
                    INSERT INTO gold.fct_cpi_daily (
                        calculation_date, coicop_division, division_name, weight,
                        division_index, headline_cpi, core_cpi, item_count, observation_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (calculation_date, coicop_division) DO UPDATE
                    SET division_name = EXCLUDED.division_name,
                        weight = EXCLUDED.weight,
                        division_index = EXCLUDED.division_index,
                        headline_cpi = EXCLUDED.headline_cpi,
                        core_cpi = EXCLUDED.core_cpi,
                        item_count = EXCLUDED.item_count,
                        observation_count = EXCLUDED.observation_count
                """, cpi_rows)

                conn.commit()
                log.info(f"✅ Successfully persisted {len(elem_rows)} elementary indices and {len(cpi_rows)} division CPI facts!")
        finally:
            conn.close()

    def compute_monthly_cpi(self, month_date: date | None = None) -> pd.DataFrame:
        """Computes conformed monthly CPI facts across all 12 COICOP divisions and headline/core indices."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                where_clause = ""
                params = []
                if month_date is not None:
                    target_month = month_date.replace(day=1)
                    where_clause = "WHERE cpi_month = %s"
                    params.append(target_month)

                query = f"""
                    WITH monthly_base AS (
                        SELECT
                            DATE_TRUNC('month', calculation_date)::DATE AS cpi_month,
                            coicop_division,
                            MAX(division_name) AS division_name,
                            MAX(weight) AS weight,
                            ROUND(AVG(division_index)::numeric, 4) AS monthly_division_index,
                            SUM(item_count) AS item_count,
                            SUM(observation_count) AS observation_count,
                            COUNT(DISTINCT calculation_date) AS active_days_in_month
                        FROM gold.fct_cpi_daily
                        GROUP BY DATE_TRUNC('month', calculation_date)::DATE, coicop_division
                    ),
                    monthly_weighted AS (
                        SELECT
                            cpi_month,
                            coicop_division,
                            division_name,
                            weight,
                            monthly_division_index,
                            ROUND(
                                (SUM(CASE WHEN monthly_division_index IS NOT NULL THEN weight * monthly_division_index ELSE 0 END) OVER (PARTITION BY cpi_month)
                                 / NULLIF(SUM(CASE WHEN monthly_division_index IS NOT NULL THEN weight ELSE 0 END) OVER (PARTITION BY cpi_month), 0))::numeric,
                                4
                            ) AS monthly_headline_cpi,
                            ROUND(
                                (SUM(CASE WHEN monthly_division_index IS NOT NULL AND coicop_division NOT IN ('01', '04', '07') THEN weight * monthly_division_index ELSE 0 END) OVER (PARTITION BY cpi_month)
                                 / NULLIF(SUM(CASE WHEN monthly_division_index IS NOT NULL AND coicop_division NOT IN ('01', '04', '07') THEN weight ELSE 0 END) OVER (PARTITION BY cpi_month), 0))::numeric,
                                4
                            ) AS monthly_core_cpi,
                            item_count,
                            observation_count,
                            active_days_in_month
                        FROM monthly_base
                    ),
                    calculated AS (
                        SELECT
                            curr.cpi_month,
                            curr.coicop_division,
                            curr.division_name,
                            curr.weight,
                            curr.monthly_division_index,
                            curr.monthly_headline_cpi,
                            curr.monthly_core_cpi,
                            -- BUG-02 FIX: Use self-joins on exact calendar intervals
                            -- instead of LAG(n) which offsets by row count, not months.
                            ROUND(((curr.monthly_division_index - mom.monthly_division_index) / NULLIF(mom.monthly_division_index, 0) * 100.0)::numeric, 4) AS mom_inflation_pct,
                            ROUND(((curr.monthly_division_index - yoy.monthly_division_index) / NULLIF(yoy.monthly_division_index, 0) * 100.0)::numeric, 4) AS yoy_inflation_pct,
                            ROUND(((curr.monthly_headline_cpi - mom.monthly_headline_cpi) / NULLIF(mom.monthly_headline_cpi, 0) * 100.0)::numeric, 4) AS headline_mom_inflation_pct,
                            ROUND(((curr.monthly_headline_cpi - yoy.monthly_headline_cpi) / NULLIF(yoy.monthly_headline_cpi, 0) * 100.0)::numeric, 4) AS headline_yoy_inflation_pct,
                            curr.item_count,
                            curr.observation_count,
                            curr.active_days_in_month
                        FROM monthly_weighted curr
                        LEFT JOIN monthly_weighted mom
                          ON mom.coicop_division = curr.coicop_division
                         AND mom.cpi_month = (curr.cpi_month - INTERVAL '1 month')::DATE
                        LEFT JOIN monthly_weighted yoy
                          ON yoy.coicop_division = curr.coicop_division
                         AND yoy.cpi_month = (curr.cpi_month - INTERVAL '1 year')::DATE
                    )
                    SELECT * FROM calculated
                    {where_clause}
                    ORDER BY cpi_month DESC, coicop_division ASC;
                """
                cur.execute(query, params)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=cols)
        finally:
            conn.close()
        return df

    def save_monthly_cpi(self, monthly_df: pd.DataFrame) -> None:
        """Upserts computed monthly CPI facts into gold.fct_cpi_monthly."""
        if monthly_df.empty:
            log.warning("No monthly CPI records to save.")
            return

        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS gold.fct_cpi_monthly (
                        cpi_month DATE NOT NULL,
                        coicop_division VARCHAR(10) NOT NULL,
                        division_name VARCHAR(150),
                        weight NUMERIC(8, 5),
                        monthly_division_index NUMERIC(10, 4),
                        monthly_headline_cpi NUMERIC(10, 4),
                        monthly_core_cpi NUMERIC(10, 4),
                        mom_inflation_pct NUMERIC(8, 4),
                        yoy_inflation_pct NUMERIC(8, 4),
                        headline_mom_inflation_pct NUMERIC(8, 4),
                        headline_yoy_inflation_pct NUMERIC(8, 4),
                        item_count INTEGER,
                        observation_count INTEGER,
                        active_days_in_month INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (cpi_month, coicop_division)
                    );
                    ALTER TABLE gold.fct_cpi_monthly ADD COLUMN IF NOT EXISTS headline_mom_inflation_pct NUMERIC(8, 4);
                    ALTER TABLE gold.fct_cpi_monthly ADD COLUMN IF NOT EXISTS headline_yoy_inflation_pct NUMERIC(8, 4);
                """)
                rows = [
                    (
                        r["cpi_month"], r["coicop_division"], r["division_name"], r["weight"],
                        None if pd.isna(r["monthly_division_index"]) else float(r["monthly_division_index"]),
                        float(r["monthly_headline_cpi"]), float(r["monthly_core_cpi"]),
                        None if pd.isna(r["mom_inflation_pct"]) else float(r["mom_inflation_pct"]),
                        None if pd.isna(r["yoy_inflation_pct"]) else float(r["yoy_inflation_pct"]),
                        None if pd.isna(r.get("headline_mom_inflation_pct")) else float(r["headline_mom_inflation_pct"]),
                        None if pd.isna(r.get("headline_yoy_inflation_pct")) else float(r["headline_yoy_inflation_pct"]),
                        int(r["item_count"]), int(r["observation_count"]), int(r["active_days_in_month"])
                    )
                    for _, r in monthly_df.iterrows()
                ]
                execute_batch(cur, """
                    INSERT INTO gold.fct_cpi_monthly (
                        cpi_month, coicop_division, division_name, weight,
                        monthly_division_index, monthly_headline_cpi, monthly_core_cpi,
                        mom_inflation_pct, yoy_inflation_pct,
                        headline_mom_inflation_pct, headline_yoy_inflation_pct,
                        item_count, observation_count, active_days_in_month
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cpi_month, coicop_division) DO UPDATE
                    SET division_name = EXCLUDED.division_name,
                        weight = EXCLUDED.weight,
                        monthly_division_index = EXCLUDED.monthly_division_index,
                        monthly_headline_cpi = EXCLUDED.monthly_headline_cpi,
                        monthly_core_cpi = EXCLUDED.monthly_core_cpi,
                        mom_inflation_pct = EXCLUDED.mom_inflation_pct,
                        yoy_inflation_pct = EXCLUDED.yoy_inflation_pct,
                        headline_mom_inflation_pct = EXCLUDED.headline_mom_inflation_pct,
                        headline_yoy_inflation_pct = EXCLUDED.headline_yoy_inflation_pct,
                        item_count = EXCLUDED.item_count,
                        observation_count = EXCLUDED.observation_count,
                        active_days_in_month = EXCLUDED.active_days_in_month
                """, rows)
                conn.commit()
                log.info(f"✅ Successfully persisted {len(rows)} monthly CPI facts into gold.fct_cpi_monthly!")
        finally:
            conn.close()

if __name__ == "__main__":
    engine = CPICalculationEngine()
    engine.run_daily_pipeline()

