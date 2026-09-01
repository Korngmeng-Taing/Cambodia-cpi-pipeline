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

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

from pipeline.config import get_database_url

log = logging.getLogger(__name__)

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

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or get_database_url()
        self.weights = DEFAULT_NIS_WEIGHTS.copy()

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
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (start_date, end_date))
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=cols)
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
            log.warning(
                "compute_jevons_index: current_prices length (%d) != base_prices length (%d). "
                "Arrays must be pre-aligned. Truncating to shorter length.",
                len(cur), len(base),
            )
        n = min(len(cur), len(base))
        cur = cur[:n]
        base = base[:n]
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
        
        base_df = df_prices[df_prices["scrape_date"] == base_date]
        if base_df.empty:
            log.warning(f"No observations found on base date {base_date}. Using earliest available.")
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
                recent_sorted = recent_obs.sort_values("scrape_date", ascending=False)
                last_prices = recent_sorted.groupby("item_id")["unit_price_khr"].first().to_dict()

                for idx, row in merged[missing_mask].iterrows():
                    item_id = row["item_id"]
                    val = last_prices.get(item_id)
                    if val is not None and not pd.isna(val) and float(val) > 0:
                        div = str(row.get("coicop_division", "01"))
                        # Apply class-mean movement ratio if available, clamped to [0.80, 1.25]
                        movement = division_movement_ratios.get(div, 1.0)
                        movement = max(0.80, min(1.25, movement))
                        imputed_price = float(val) * movement
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

    def aggregate_division_and_headline(self, elementary_df: pd.DataFrame, calc_date: date) -> tuple[pd.DataFrame, dict]:
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
            headline_cpi = 100.0
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

    def run_daily_pipeline(self, target_date: date | None = None, base_date: date | None = None):
        """Executes full daily CPI calculation and writes results to PostgreSQL."""
        if target_date is None:
            target_date = date.today()

        log.info(f"🚀 Running Daily CPI Calculation for {target_date} (Base Date: {base_date})")

        # When base_date is unset, infer it as the earliest scrape_date with data.
        # Probe with a wide historical window first so we can pick the right base.
        if base_date is None:
            probe_start = target_date - timedelta(days=365 * 5)  # 5-year retrospective
            df_history = self.load_clean_prices(probe_start, target_date)
            if df_history.empty:
                log.error("No price history available to infer base_date.")
                return
            base_date = df_history['scrape_date'].min()
            base_obs = int(df_history[df_history['scrape_date'] == base_date]['unit_price_khr'].count())
            log.info(f"🔧 No base_date provided; using earliest available date {base_date} as base period (obs={base_obs}).")
        else:
            df_history = self.load_clean_prices(base_date, target_date)

        if df_history.empty:
            log.error(f"No clean price data available between {base_date} and {target_date}")
            return

        base_df = self.compute_base_prices(base_date, df_history)
        elementary_df = self.compute_daily_elementary_indices(target_date, base_df, df_history)

        df_div, headline = self.aggregate_division_and_headline(elementary_df, target_date)

        log.info(f"📊 {target_date} Headline CPI: {headline['headline_cpi']:.2f} | Core CPI: {headline['core_cpi']:.2f} | Active Basket Items: {headline['total_items']}")

        self._save_to_database(elementary_df, df_div, headline)

    def _save_to_database(self, elementary_df: pd.DataFrame, df_div: pd.DataFrame, headline: dict):
        """Persists elementary indices and daily CPI facts to PostgreSQL."""
        with self.get_connection() as conn:
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

    def compute_monthly_cpi(self, month_date: date | None = None) -> pd.DataFrame:
        """Computes conformed monthly CPI facts across all 12 COICOP divisions and headline/core indices."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                where_clause = ""
                params = []
                if month_date is not None:
                    target_month = month_date.replace(day=1)
                    where_clause = "WHERE DATE_TRUNC('month', calculation_date)::DATE = %s"
                    params.append(target_month)

                query = f"""
                    WITH monthly_base AS (
                        SELECT
                            DATE_TRUNC('month', calculation_date)::DATE AS cpi_month,
                            coicop_division,
                            MAX(division_name) AS division_name,
                            MAX(weight) AS weight,
                            ROUND(AVG(division_index)::numeric, 4) AS monthly_division_index,
                            ROUND(AVG(headline_cpi)::numeric, 4) AS monthly_headline_cpi,
                            ROUND(AVG(core_cpi)::numeric, 4) AS monthly_core_cpi,
                            SUM(item_count) AS item_count,
                            SUM(observation_count) AS observation_count,
                            COUNT(DISTINCT calculation_date) AS active_days_in_month
                        FROM gold.fct_cpi_daily
                        {where_clause}
                        GROUP BY DATE_TRUNC('month', calculation_date)::DATE, coicop_division
                    )
                    SELECT
                        cpi_month,
                        coicop_division,
                        division_name,
                        weight,
                        monthly_division_index,
                        monthly_headline_cpi,
                        monthly_core_cpi,
                        ROUND(((monthly_division_index - LAG(monthly_division_index) OVER (PARTITION BY coicop_division ORDER BY cpi_month)) / NULLIF(LAG(monthly_division_index) OVER (PARTITION BY coicop_division ORDER BY cpi_month), 0) * 100.0)::numeric, 4) AS mom_inflation_pct,
                        ROUND(((monthly_division_index - LAG(monthly_division_index, 12) OVER (PARTITION BY coicop_division ORDER BY cpi_month)) / NULLIF(LAG(monthly_division_index, 12) OVER (PARTITION BY coicop_division ORDER BY cpi_month), 0) * 100.0)::numeric, 4) AS yoy_inflation_pct,
                        item_count,
                        observation_count,
                        active_days_in_month
                    FROM monthly_base
                    ORDER BY cpi_month DESC, coicop_division ASC;
                """
                cur.execute(query, params)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=cols)
                return df

    def save_monthly_cpi(self, monthly_df: pd.DataFrame) -> None:
        """Upserts computed monthly CPI facts into gold.fct_cpi_monthly."""
        if monthly_df.empty:
            log.warning("No monthly CPI records to save.")
            return

        with self.get_connection() as conn:
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
                        item_count INTEGER,
                        observation_count INTEGER,
                        active_days_in_month INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (cpi_month, coicop_division)
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_fct_cpi_monthly ON gold.fct_cpi_monthly (cpi_month, coicop_division);
                """)
                rows = [
                    (
                        r["cpi_month"], r["coicop_division"], r["division_name"], r["weight"],
                        None if pd.isna(r["monthly_division_index"]) else float(r["monthly_division_index"]),
                        float(r["monthly_headline_cpi"]), float(r["monthly_core_cpi"]),
                        None if pd.isna(r["mom_inflation_pct"]) else float(r["mom_inflation_pct"]),
                        None if pd.isna(r["yoy_inflation_pct"]) else float(r["yoy_inflation_pct"]),
                        int(r["item_count"]), int(r["observation_count"]), int(r["active_days_in_month"])
                    )
                    for _, r in monthly_df.iterrows()
                ]
                execute_batch(cur, """
                    INSERT INTO gold.fct_cpi_monthly (
                        cpi_month, coicop_division, division_name, weight,
                        monthly_division_index, monthly_headline_cpi, monthly_core_cpi,
                        mom_inflation_pct, yoy_inflation_pct,
                        item_count, observation_count, active_days_in_month
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cpi_month, coicop_division) DO UPDATE
                    SET division_name = EXCLUDED.division_name,
                        weight = EXCLUDED.weight,
                        monthly_division_index = EXCLUDED.monthly_division_index,
                        monthly_headline_cpi = EXCLUDED.monthly_headline_cpi,
                        monthly_core_cpi = EXCLUDED.monthly_core_cpi,
                        mom_inflation_pct = EXCLUDED.mom_inflation_pct,
                        yoy_inflation_pct = EXCLUDED.yoy_inflation_pct,
                        item_count = EXCLUDED.item_count,
                        observation_count = EXCLUDED.observation_count,
                        active_days_in_month = EXCLUDED.active_days_in_month
                """, rows)
                conn.commit()
                log.info(f"✅ Successfully persisted {len(rows)} monthly CPI facts into gold.fct_cpi_monthly!")

if __name__ == "__main__":
    engine = CPICalculationEngine()
    engine.run_daily_pipeline()

