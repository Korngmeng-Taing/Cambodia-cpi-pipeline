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
    "05": 0.02743,  # Furnishings & Household Maintenance (2.743%)
    "06": 0.05141,  # Health & Pharmaceuticals (5.141%)
    "07": 0.12228,  # Transport & Automotive Fuels (12.228%)
    "08": 0.01136,  # Communication & Telecom (1.136%)
    "09": 0.02912,  # Recreation & Culture (2.912%)
    "10": 0.01174,  # Education (1.174%)
    "11": 0.05861,  # Restaurants & Hotels (5.861%)
    "12": 0.02285,  # Miscellaneous Goods & Services (2.285%)
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

# Sibling and child COICOP codes mapped hierarchically to official 2006 NIS Cambodia leaf classes
DEFAULT_COICOP_CLASS_MAPPING = {
    # Division 02
    "02.2.1": "02.2.0",  # Cigarettes/tobacco -> Tobacco
    # Division 03
    "03.1.1": "03.1.3",  # Clothing materials -> Other articles of clothing
    "03.1.4": "03.1.3",  # Cleaning/repair of clothing -> Other articles of clothing
    # Division 05
    "05.3.1": "05.1.1",  # Major appliances -> Furniture and furnishings
    "05.4.0": "05.5.1",  # Glassware/tableware -> Glassware, tableware, utensils
    "05.4.1": "05.5.1",  # Glassware/tableware -> Glassware, tableware, utensils
    "05.5.2": "05.5.1",  # Small tools -> Glassware, tableware, utensils
    "05.6.2": "05.6.1",  # Domestic services -> Non-durable household goods
    # Division 06
    "06.1.3": "06.1.2",  # Other medical products -> Other medical products
    "06.1.4": "06.1.2",  # Diagnostic products -> Other medical products
    "06.2.2": "06.2.1",  # Outpatient dental -> Medical services
    "06.3.1": "06.2.1",  # Hospital services -> Medical services
    # Division 07
    "07.1.1": "07.1.2",  # Motor cars -> Motorcycles (purchase of vehicles)
    "07.2.1": "07.2.3",  # Spare parts -> Maintenance and repair
    "07.3.1": "07.3.2",  # Passenger railway -> Passenger transport by bus/coach
    # Division 08
    "08.1.1": "08.3.0",  # Postal services -> Telephone and internet services
    # Division 09
    "09.2.1": "09.1.1",  # Major durables -> Audio/visual equipment
    "09.3.2": "09.3.1",  # Sport/camping equipment -> Games, toys and hobbies
    "09.3.3": "09.3.1",  # Gardens/plants -> Games, toys and hobbies
    "09.3.4": "09.3.1",  # Pet products -> Games, toys and hobbies
    "09.5.4": "09.5.1",  # Stationery and drawing materials -> Books and stationery
    # Division 10
    "10.1.1": "10.1.0",  # Educational stationery & textbooks -> Education
    "10.2.0": "10.1.0",  # Education materials -> Education
    # Division 12
    "12.1.2": "12.1.3",  # Electrical personal care appliances -> Other personal care
    "12.2.0": "12.3.2",  # Personal effects / services -> Other personal effects
    "12.2.1": "12.3.2",  # Personal effects -> Other personal effects
    "12.2.9": "12.3.2",  # Personal effects -> Other personal effects
    "12.4.0": "12.3.2",  # Social protection -> Other personal effects
    # COICOP 2018 Division 13 (Personal Care) mapped to 1999/NIS Division 12
    "13.1.1": "12.1.1",  # Hairdressing -> Hairdressing salons
    "13.1.2": "12.1.3",  # Personal care articles/hygiene -> Other personal care
    "13.2.1": "12.3.1",  # Jewellery & watches -> Jewellery, clocks and watches
    "13.2.9": "12.3.2",  # Other personal effects -> Other personal effects
    "13.9.0": "12.3.2",  # Other personal goods -> Other personal effects
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
                # Strictly filter for Class-level breakdown rows only to prevent Group/Division double-counting
                if "coicop_level" in df.columns:
                    df = df[df["coicop_level"].astype(str).str.strip().str.lower() == "class"]
                for _, row in df.iterrows():
                    code = str(row.get("coicop_code", "")).strip()
                    wt = row.get("weight_pct")
                    if code and not pd.isna(wt) and float(wt) > 0:
                        weights[code] = float(wt)
            except Exception as e:
                log.warning("Could not load subclass weights from seed CSV: %s", e)
        return weights

    def _get_subclass_code(self, raw_code: str | None, div_code: str) -> str:
        """Resolves raw COICOP code into an official subclass / class code matching weights.
        Implements automatic hierarchical roll-up: if a 5-digit code isn't in the weights,
        it tries the 4-digit and 3-digit parents.
        """
        if raw_code is None or pd.isna(raw_code):
            return f"{div_code}.unclassified"
        code = str(raw_code).strip()
        if not code:
            return f"{div_code}.unclassified"

        # 1. Exact match (checks 5-digit, then 4-digit, etc. based on weights table)
        if code in self.subclass_weights:
            return code

        # 2. Hierarchical Roll-up (Strip lowest digit until a weight match is found)
        # Example: 01.1.1.1 -> 01.1.1 -> 01.1 -> 01
        parts = code.split('.')
        for i in range(len(parts)-1, 0, -1):
            parent_code = '.'.join(parts[:i])
            if parent_code in self.subclass_weights:
                return parent_code

        # 3. Manual mapping for known anomalies
        if code in DEFAULT_COICOP_CLASS_MAPPING:
            return DEFAULT_COICOP_CLASS_MAPPING[code]

        # 4. Fallback: unclassified division bucket
        return f"{div_code}.unclassified"

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
                COALESCE(h.hedonic_adjusted_price_khr, s.unit_price_khr) AS unit_price_khr,
                COALESCE(h.hedonic_adjusted_price_khr, s.price_khr) AS price_khr,
                s.original_price_khr,
                s.on_promo,
                s.discount_pct,
                COALESCE(ci.coicop_division, s.coicop_division) AS coicop_division,
                COALESCE(ci.coicop_code, s.coicop_code) AS coicop_code,
                s.is_outlier
            FROM silver.clean_store_prices s
            LEFT JOIN silver.canonical_items ci
              ON ci.item_id::text = s.item_id::text
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
        df["price_khr"] = pd.to_numeric(df["price_khr"], errors="coerce")
        df["unit_price_khr"] = pd.to_numeric(df["unit_price_khr"], errors="coerce")
        if "original_price_khr" in df.columns:
            df["original_price_khr"] = pd.to_numeric(df["original_price_khr"], errors="coerce")
        if "discount_pct" in df.columns:
            df["discount_pct"] = pd.to_numeric(df["discount_pct"], errors="coerce")
        
        # Normalize coicop_division to clean 2-digit format (01-12) or truncate anomalies
        def _clean_div(val):
            if pd.isna(val) or not str(val).strip():
                return "01"
            s = str(val).strip()
            if s.upper() == "UNCLASSIFIED":
                return "01"
            if s.isdigit():
                return s.zfill(2)[:2]
            return s[:2]

        df["coicop_division"] = df["coicop_division"].apply(_clean_div)

        # Only accept metric unit prices for grocery and consumable divisions
        # For non-consumable divisions (03, 04, 07, 08, 09, 10, 11), sizes like "5G" or "2.4G"
        # are electronic specs, not weight/volume.
        consumable_divisions = {"01", "02", "05", "06", "12"}
        is_consumable = df["coicop_division"].isin(consumable_divisions)
        df.loc[~is_consumable, "unit_price_khr"] = np.nan

        df = df[df["price_khr"] > 0]
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

    def compute_base_prices(
        self, 
        base_date: date, 
        df_prices: pd.DataFrame | None = None,
        base_window_days: int = 7
    ) -> pd.DataFrame:
        """
        Computes the base geometric mean price per item_id on the base date or launch window.
        Follows ILO CPI Manual §6.30 (Multi-Day Baseline Window & Expanding Universe):
        1. Items observed on base_date establish their base price directly.
        2. Items from newly launched stores or newer items (e.g. BookMeBus, RedBus, Grab UCare)
           establish their reference base price on their first appearance.
        3. Tracks both shelf price and metric unit price for strict dimensional comparison.
        """
        if df_prices is None:
            df_prices = self.load_clean_prices(base_date, base_date + timedelta(days=base_window_days))
        
        if df_prices.empty:
            log.warning("No price history available to compute base prices.")
            return pd.DataFrame(columns=["item_id", "coicop_division", "coicop_code", "base_price_khr", "base_unit_price_khr", "base_obs_count", "first_seen_date"])

        # Determine reference date per item: earliest observed scrape_date >= base_date
        valid_prices = df_prices[df_prices["scrape_date"] >= base_date].copy()
        if valid_prices.empty:
            valid_prices = df_prices.copy()

        earliest_dates = valid_prices.groupby("item_id")["scrape_date"].min().reset_index()
        base_df = pd.merge(valid_prices, earliest_dates, on=["item_id", "scrape_date"], how="inner")
        base_df["first_seen_date"] = base_df["scrape_date"]

        if base_df.empty:
            return pd.DataFrame(columns=["item_id", "coicop_division", "coicop_code", "base_price_khr", "base_unit_price_khr", "base_obs_count", "first_seen_date"])

        if "price_khr" not in base_df.columns and "unit_price_khr" in base_df.columns:
            base_df = base_df.copy()
            base_df["price_khr"] = base_df["unit_price_khr"]
        elif "unit_price_khr" not in base_df.columns and "price_khr" in base_df.columns:
            base_df = base_df.copy()
            base_df["unit_price_khr"] = base_df["price_khr"]

        # Strategy A: Base Price Promo Regularization (ILO CPI Manual §6.82)
        # Deep clearance promotions on the base date distort base prices downward.
        # If an observation on base date has on_promo == True and discount_pct >= 45% (or original_price_khr >= 1.45 * price_khr),
        # use original regular MSRP shelf price to compute base prices.
        if "on_promo" in base_df.columns and "original_price_khr" in base_df.columns:
            orig = pd.to_numeric(base_df["original_price_khr"], errors="coerce")
            disc = pd.to_numeric(base_df.get("discount_pct", pd.Series(0, index=base_df.index)), errors="coerce").fillna(0)
            is_promo = base_df["on_promo"].fillna(False).astype(bool)
            is_deep_promo = (
                is_promo &
                ((disc >= 45.0) | (orig >= base_df["price_khr"] * 1.45)) &
                (orig > base_df["price_khr"])
            )
            if is_deep_promo.any():
                base_df = base_df.copy()
                promo_factor = np.where(
                    is_deep_promo,
                    orig / base_df["price_khr"],
                    1.0
                )
                base_df["price_khr"] = np.where(is_deep_promo, orig, base_df["price_khr"])
                if "unit_price_khr" in base_df.columns:
                    base_df["unit_price_khr"] = np.where(
                        is_deep_promo & base_df["unit_price_khr"].notna(),
                        base_df["unit_price_khr"] * promo_factor,
                        base_df["unit_price_khr"]
                    )

        def _safe_geom_mean(x):
            valid = x[x > 0].dropna()
            if len(valid) == 0:
                return np.nan
            if len(valid) > 2:
                vals = valid.to_numpy()
                med_v = float(np.median(vals))
                if med_v > 0:
                    # Robust trimmed filter: exclude prices outside [0.4 * median, 2.5 * median]
                    inliers = vals[(vals >= med_v * 0.4) & (vals <= med_v * 2.5)]
                    if len(inliers) > 0:
                        return float(np.exp(np.mean(np.log(inliers))))
            return float(np.exp(np.mean(np.log(valid))))

        grouped = base_df.groupby("item_id").agg(
            coicop_division=("coicop_division", "first"),
            coicop_code=("coicop_code", "first"),
            base_price_khr=("price_khr", _safe_geom_mean),
            base_unit_price_khr=("unit_price_khr", _safe_geom_mean),
            base_obs_count=("price_khr", "count"),
            first_seen_date=("first_seen_date", "first")
        ).reset_index()

        return grouped[grouped["base_price_khr"] > 0]

    def load_or_create_base_registry(self, base_date: date, df_base: pd.DataFrame) -> pd.DataFrame:
        """Loads canonical baseline prices from gold.dim_item_base_prices, populating it if empty."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS gold.dim_item_base_prices (
                        item_id TEXT PRIMARY KEY,
                        coicop_division VARCHAR(10) NOT NULL,
                        coicop_code VARCHAR(20),
                        base_price_khr NUMERIC(14, 4) NOT NULL,
                        base_unit_price_khr NUMERIC(14, 4),
                        base_obs_count INTEGER DEFAULT 1,
                        first_seen_date DATE NOT NULL,
                        enrolled_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_item_base_prices_division ON gold.dim_item_base_prices(coicop_division);
                    CREATE INDEX IF NOT EXISTS idx_item_base_prices_first_seen ON gold.dim_item_base_prices(first_seen_date);
                """)
                cur.execute("SELECT item_id, coicop_division, coicop_code, base_price_khr, base_unit_price_khr, base_obs_count, first_seen_date FROM gold.dim_item_base_prices;")
                rows = cur.fetchall()
                if rows:
                    cols = ["item_id", "coicop_division", "coicop_code", "base_price_khr", "base_unit_price_khr", "base_obs_count", "first_seen_date"]
                    return pd.DataFrame(rows, columns=cols)

                # Initialize registry from base period prices
                computed = self.compute_base_prices(base_date, df_base)
                if not computed.empty:
                    insert_rows = [
                        (
                            str(r.item_id), str(r.coicop_division), str(r.coicop_code) if pd.notna(r.coicop_code) else None,
                            float(r.base_price_khr), float(r.base_unit_price_khr) if pd.notna(r.base_unit_price_khr) else float(r.base_price_khr),
                            int(r.base_obs_count) if hasattr(r, "base_obs_count") and pd.notna(r.base_obs_count) else 1,
                            r.first_seen_date if pd.notna(r.first_seen_date) else base_date
                        )
                        for r in computed.itertuples(index=False)
                    ]
                    execute_batch(cur, """
                        INSERT INTO gold.dim_item_base_prices (
                            item_id, coicop_division, coicop_code, base_price_khr, base_unit_price_khr, base_obs_count, first_seen_date
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (item_id) DO NOTHING;
                    """, insert_rows, page_size=1000)
                    conn.commit()
                return computed
        except Exception as e:
            log.warning("Could not interact with gold.dim_item_base_prices (%s); computing in-memory base prices.", e)
            return self.compute_base_prices(base_date, df_base)
        finally:
            conn.close()

    def enroll_new_base_items(self, new_items: pd.DataFrame, enrollment_date: date) -> None:
        """Persists newly observed items into gold.dim_item_base_prices to permanently anchor their base price."""
        if new_items.empty:
            return
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                rows = [
                    (
                        str(r["item_id"]),
                        str(r.get("coicop_division") or "01"),
                        str(r.get("coicop_code")) if pd.notna(r.get("coicop_code")) else None,
                        float(r["base_price_khr"]),
                        float(r["base_unit_price_khr"]) if pd.notna(r.get("base_unit_price_khr")) else float(r["base_price_khr"]),
                        int(r.get("base_obs_count", 1)),
                        enrollment_date
                    )
                    for _, r in new_items.iterrows()
                    if pd.notna(r.get("base_price_khr")) and float(r["base_price_khr"]) > 0
                ]
                if rows:
                    execute_batch(cur, """
                        INSERT INTO gold.dim_item_base_prices (
                            item_id, coicop_division, coicop_code, base_price_khr, base_unit_price_khr, base_obs_count, first_seen_date
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (item_id) DO NOTHING;
                    """, rows, page_size=1000)
                    conn.commit()
                    log.info("Permanently enrolled %d new items into gold.dim_item_base_prices on %s", len(rows), enrollment_date)
        except Exception as e:
            log.warning("Failed to persist newly enrolled base items to DB (%s). In-memory base price used.", e)
        finally:
            conn.close()

    def compute_daily_elementary_indices(
        self, 
        calc_date: date, 
        base_df: pd.DataFrame, 
        df_history: pd.DataFrame,
        imputation_window_days: int = 7
    ) -> pd.DataFrame:
        """
        Computes elementary Jevons price indices for calc_date with ILO Class-Mean Imputation.
        Enforces strict pure-price dimensional comparison (P_t / P_0):
          - Compares unit_price_khr (per kg/L) if BOTH base and current have valid metric units.
          - Falls back to shelf price_khr (per pack/can/jar) if either is unnormalized.
        When an item is missing on day t (gap <= 7 days), its price is advanced using the
        geometric average rate of change of observed items in the same COICOP division.
        """
        base_df = base_df.copy()
        if "first_seen_date" in base_df.columns:
            base_df = base_df[base_df["first_seen_date"] <= calc_date].copy()

        if "base_unit_price_khr" not in base_df.columns and "base_price_khr" in base_df.columns:
            base_df["base_unit_price_khr"] = base_df["base_price_khr"]
        elif "base_price_khr" not in base_df.columns and "base_unit_price_khr" in base_df.columns:
            base_df["base_price_khr"] = base_df["base_unit_price_khr"]

        df_history = df_history.copy()
        if "price_khr" not in df_history.columns and "unit_price_khr" in df_history.columns:
            df_history["price_khr"] = df_history["unit_price_khr"]
        elif "unit_price_khr" not in df_history.columns and "price_khr" in df_history.columns:
            df_history["unit_price_khr"] = df_history["price_khr"]

        def _safe_geom_mean(x):
            valid = x[x > 0].dropna()
            if len(valid) == 0:
                return np.nan
            if len(valid) > 2:
                vals = valid.to_numpy()
                med_v = float(np.median(vals))
                if med_v > 0:
                    inliers = vals[(vals >= med_v * 0.4) & (vals <= med_v * 2.5)]
                    if len(inliers) > 0:
                        return float(np.exp(np.mean(np.log(inliers))))
            return float(np.exp(np.mean(np.log(valid))))

        # Current day observations strictly per unique item_id
        today_obs = df_history[df_history["scrape_date"] == calc_date]
        today_agg = today_obs.groupby("item_id").agg(
            today_price_khr=("price_khr", _safe_geom_mean),
            today_unit_price_khr=("unit_price_khr", _safe_geom_mean),
            observation_count=("price_khr", "count")
        ).reset_index()

        # Dynamic expansion: If an item in today_agg is NOT in base_df, enroll it dynamically
        missing_mask = ~today_agg["item_id"].isin(base_df["item_id"])
        if missing_mask.any():
            missing_today = today_agg[missing_mask]
            cols = ["item_id", "coicop_division", "coicop_code"]
            lookup = today_obs[cols].drop_duplicates("item_id")
            new_items = pd.merge(missing_today, lookup, on="item_id", how="left")
            new_items["base_price_khr"] = new_items["today_price_khr"]
            new_items["base_unit_price_khr"] = new_items["today_unit_price_khr"]
            new_items["base_obs_count"] = new_items["observation_count"]
            new_items["first_seen_date"] = calc_date
            # Persist newly enrolled items to gold.dim_item_base_prices so baseline is permanently anchored
            self.enroll_new_base_items(new_items, calc_date)
            new_items = new_items.drop(columns=["today_price_khr", "today_unit_price_khr", "observation_count"], errors="ignore")
            base_df = pd.concat([base_df, new_items], ignore_index=True)

        # Merge with base prices on item_id
        merged = pd.merge(base_df, today_agg, on="item_id", how="left")
        merged["is_imputed"] = False

        # Pure Price Comparison (ILO CPI Manual):
        # 1. Use metric unit prices (KHR/kg, KHR/L) if BOTH base and today have valid metric unit prices (> 0).
        # 2. Guard against wholesale case / pack_qty parsing mismatch:
        #    If unit_ratio diverges wildly (>= 3.0x or <= 0.33x) while shelf_ratio is stable (0.70 to 1.40),
        #    that is a package-count parsing artifact (e.g. 24X case title priced as single unit). Fall back to shelf price.
        # 3. If EITHER is missing metric unit price, fall back to shelf price (price_khr) for BOTH.
        has_both_unit = (
            merged["base_unit_price_khr"].notna() & (merged["base_unit_price_khr"] > 0) &
            merged["today_unit_price_khr"].notna() & (merged["today_unit_price_khr"] > 0)
        )
        shelf_ratio = np.where(merged["base_price_khr"] > 0, merged["today_price_khr"] / merged["base_price_khr"], 1.0)
        unit_ratio = np.where(has_both_unit, merged["today_unit_price_khr"] / merged["base_unit_price_khr"], shelf_ratio)
        is_pack_artifact = has_both_unit & ((unit_ratio >= 3.0) | (unit_ratio <= 0.33)) & (shelf_ratio >= 0.70) & (shelf_ratio <= 1.40)
        use_unit_price = has_both_unit & ~is_pack_artifact

        merged["base_price_khr"] = np.where(use_unit_price, merged["base_unit_price_khr"], merged["base_price_khr"])
        merged["current_price_khr"] = np.where(use_unit_price, merged["today_unit_price_khr"], merged["today_price_khr"])

        # Compute division movement ratios for observed items between yesterday and today
        prior_dates = sorted([d for d in df_history["scrape_date"].unique() if d < calc_date])
        prev_date = prior_dates[-1] if prior_dates else None
        
        division_movement_ratios: dict[str, float] = {}
        subclass_movement_ratios: dict[str, float] = {}
        if prev_date is not None and not today_obs.empty:
            prev_obs = df_history[df_history["scrape_date"] == prev_date]
            prev_agg = prev_obs.groupby("item_id").agg(
                prev_price_khr=("price_khr", _safe_geom_mean),
                prev_unit_price_khr=("unit_price_khr", _safe_geom_mean)
            ).reset_index()
            
            # Common items between yesterday and today
            common = pd.merge(today_agg, prev_agg, on="item_id")
            if not common.empty:
                cols_to_merge = ["item_id", "coicop_division", "base_unit_price_khr"]
                if "coicop_code" in base_df.columns:
                    cols_to_merge.append("coicop_code")
                common = pd.merge(common, base_df[cols_to_merge], on="item_id", how="left")
                comm_both_unit = (
                    common["today_unit_price_khr"].notna() & (common["today_unit_price_khr"] > 0) &
                    common["prev_unit_price_khr"].notna() & (common["prev_unit_price_khr"] > 0)
                )
                today_eval = np.where(comm_both_unit, common["today_unit_price_khr"], common["today_price_khr"])
                prev_eval = np.where(comm_both_unit, common["prev_unit_price_khr"], common["prev_price_khr"])
                common["ratio"] = today_eval / prev_eval
                common = common[(common["ratio"] >= 0.5) & (common["ratio"] <= 2.0)]
                for div, group in common.groupby("coicop_division"):
                    if len(group) > 0:
                        division_movement_ratios[str(div)] = float(np.exp(np.mean(np.log(group["ratio"]))))
                if "coicop_code" in common.columns:
                    for sc, group in common.groupby("coicop_code"):
                        if len(group) >= 2 and pd.notna(sc) and str(sc).strip():
                            subclass_movement_ratios[str(sc).strip()] = float(np.exp(np.mean(np.log(group["ratio"]))))

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
                latest_dates_dict = dict(zip(latest_dates["item_id"], latest_dates["scrape_date"], strict=False))
                latest_obs = pd.merge(
                    recent_obs, latest_dates, on=["item_id", "scrape_date"], how="inner"
                )
                
                base_unit_lookup = dict(zip(base_df["item_id"], base_df["base_unit_price_khr"], strict=False))
                base_shelf_lookup = dict(zip(base_df["item_id"], base_df["base_price_khr"], strict=False))
                latest_agg = latest_obs.groupby("item_id").agg(
                    last_price_khr=("price_khr", _safe_geom_mean),
                    last_unit_price_khr=("unit_price_khr", _safe_geom_mean)
                ).reset_index()

                last_prices = {}
                matched_base_prices = {}
                for r in latest_agg.itertuples():
                    b_unit = base_unit_lookup.get(r.item_id)
                    s_b = base_shelf_lookup.get(r.item_id)
                    s_c = r.last_price_khr
                    if pd.notna(b_unit) and b_unit > 0 and pd.notna(r.last_unit_price_khr) and r.last_unit_price_khr > 0:
                        s_ratio = (s_c / s_b) if (s_b and s_b > 0 and s_c and s_c > 0) else 1.0
                        u_ratio = r.last_unit_price_khr / b_unit
                        if (u_ratio >= 3.0 or u_ratio <= 0.33) and (0.70 <= s_ratio <= 1.40):
                            last_prices[r.item_id] = s_c
                            matched_base_prices[r.item_id] = s_b
                        else:
                            last_prices[r.item_id] = r.last_unit_price_khr
                            matched_base_prices[r.item_id] = b_unit
                    else:
                        last_prices[r.item_id] = r.last_price_khr
                        matched_base_prices[r.item_id] = s_b

                imputed_curr = {}
                imputed_base = {}
                imputable_mask = missing_mask & merged["item_id"].isin(last_prices.keys())
                for r in merged[imputable_mask].itertuples():
                    item_id = r.item_id
                    val = last_prices.get(item_id)
                    b_price = matched_base_prices.get(item_id)
                    if val is not None and not pd.isna(val) and float(val) > 0:
                        div = str(getattr(r, "coicop_division", "01"))
                        sc = str(getattr(r, "coicop_code", "")).strip() if pd.notna(getattr(r, "coicop_code", None)) else ""
                        # Two-tier ILO Class-Mean Imputation:
                        # Tier 1: Subclass-level geometric movement if available
                        # Tier 2: Division-level geometric movement fallback
                        # Under ILO CPI Manual §6.58, advance the item's previous price
                        # using the class price movement relative to previous period.
                        if sc and sc in subclass_movement_ratios:
                            movement = subclass_movement_ratios[sc]
                        else:
                            movement = division_movement_ratios.get(div, 1.0)
                        movement = max(0.80, min(1.25, movement))

                        last_obs_date = latest_dates_dict.get(item_id)
                        if last_obs_date is not None:
                            days_gap = (pd.to_datetime(calc_date) - pd.to_datetime(last_obs_date)).days
                            days_gap = max(1, min(days_gap, 7))
                        else:
                            days_gap = 1
                        # Advance from last observed price using the class/division movement.
                        # Do not compound movement exponentially over multiple days (movement ** days_gap)
                        # as movement is calculated day-over-day and exponential compounding creates severe
                        # distortion on multi-day gaps.
                        imputed_curr[item_id] = float(val) * movement
                        if b_price is not None and pd.notna(b_price) and float(b_price) > 0:
                            imputed_base[item_id] = float(b_price)

                if imputed_curr:
                    s_curr = merged["item_id"].map(imputed_curr)
                    has_imp = s_curr.notna()
                    merged.loc[has_imp, "current_price_khr"] = s_curr[has_imp]
                    merged.loc[has_imp, "observation_count"] = 1
                    merged.loc[has_imp, "is_imputed"] = True
                    s_base = merged["item_id"].map(imputed_base)
                    has_base_imp = s_base.notna()
                    merged.loc[has_base_imp, "base_price_khr"] = s_base[has_base_imp]

        # Drop items that are still missing (missing > 7 days)
        valid = merged.dropna(subset=["current_price_khr", "base_price_khr"]).copy()
        valid = valid[(valid["current_price_khr"] > 0) & (valid["base_price_khr"] > 0)]
        valid["price_ratio"] = valid["current_price_khr"] / valid["base_price_khr"]
        
        # Dual-tier Outlier Filter:
        # Tier 1: Global ILO bounds [0.20, 4.00]
        # Tier 2: Median Absolute Deviation (MAD) on log price ratios per division (ILO CPI Manual §10.32)
        valid = self.filter_statistical_outliers_mad(valid, group_col="coicop_division", z_threshold=3.5)

        # Store price ratio as a percentage (per-item Jevons index)
        valid["price_ratio_pct"] = valid["price_ratio"] * 100.0
        valid["elementary_index"] = valid["price_ratio_pct"]
        valid["calculation_date"] = calc_date

        return valid

    @staticmethod
    def filter_statistical_outliers_mad(
        df: pd.DataFrame,
        group_col: str = "coicop_division",
        z_threshold: float = 3.5,
    ) -> pd.DataFrame:
        """
        Filters price ratio outliers using Median Absolute Deviation (MAD) on log price ratios
        (ILO CPI Manual 2020 §10.32; Diewert 1995).

        For each group:
            log_r = ln(price_ratio)
            med = median(log_r)
            mad = median(|log_r - med|)
            robust_sigma = 1.4826 * mad
            outlier if |log_r - med| > z_threshold * robust_sigma
        When group size is small (N < 5) or mad == 0, falls back to conservative
        bounds: 0.33 <= price_ratio <= 3.00.
        """
        if df.empty or "price_ratio" not in df.columns:
            return df

        clean_indices = []
        for _, group in df.groupby(group_col, observed=True):
            ratios = group["price_ratio"].to_numpy()
            n = len(ratios)

            # Global guardrails (catches 10x-100x decimal glitches)
            base_mask = (ratios >= 0.20) & (ratios <= 4.00)

            if n >= 5:
                log_r = np.log(ratios)
                med = np.median(log_r)
                mad = np.median(np.abs(log_r - med))
                if mad > 1e-6:
                    robust_sigma = 1.4826 * mad
                    mad_mask = np.abs(log_r - med) <= (z_threshold * robust_sigma)
                    keep_mask = base_mask & mad_mask
                else:
                    keep_mask = base_mask & (ratios >= 0.33) & (ratios <= 3.00)
            else:
                keep_mask = base_mask & (ratios >= 0.33) & (ratios <= 3.00)

            clean_indices.extend(group.index[keep_mask])

        return df.loc[clean_indices].copy()

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
                    div_items_with_sub = div_items.copy()
                    div_items_with_sub["subclass_code"] = div_items_with_sub["coicop_code"].apply(
                        lambda c, d=div_code: self._get_subclass_code(c, d)
                    )

                    valid_sub_items = div_items_with_sub[div_items_with_sub["price_ratio"] > 0]
                    if not valid_sub_items.empty:
                        # Vectorized Jevons geometric-mean per subclass
                        subclass_series = valid_sub_items.groupby("subclass_code")["price_ratio"].apply(
                            lambda s: float(np.exp(np.mean(np.log(s))) * 100.0)
                        )
                        subclass_indices = subclass_series.tolist()
                        subclass_wts = [self.subclass_weights.get(sc) for sc in subclass_series.index]
                        # Resilient Laspeyres weighting across subclasses
                        valid_pairs = [
                            (idx, wt) for idx, wt in zip(subclass_indices, subclass_wts, strict=False)
                            if wt is not None and wt > 0
                        ]
                        if valid_pairs:
                            sum_valid_wts = sum(wt for _, wt in valid_pairs)
                            div_index = sum(idx * wt for idx, wt in valid_pairs) / sum_valid_wts
                        else:
                            # Fallback only if no valid subclass weights exist: unweighted geometric mean
                            div_index = float(np.exp(np.mean(np.log(div_items["price_ratio"]))) * 100.0)
                    else:
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

        # Load base period observations to compute or initialize baseline registry
        df_base = self.load_clean_prices(base_date, base_date)
        # Load or initialize persistent baseline reference prices from gold.dim_item_base_prices
        base_df = self.load_or_create_base_registry(base_date, df_base)
        if base_df.empty:
            log.error(f"No baseline prices available for base date {base_date}")
            return

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
                    CREATE INDEX IF NOT EXISTS idx_fct_cpi_daily_calc_date ON gold.fct_cpi_daily (calculation_date);
                    CREATE INDEX IF NOT EXISTS idx_fct_elem_indices_calc_date ON gold.fct_elementary_indices (calculation_date);
                """)

                # Ensure price_ratio_pct and elementary_index columns exist and are synced
                cur.execute("""
                    DO $$ BEGIN
                        ALTER TABLE gold.fct_elementary_indices ADD COLUMN IF NOT EXISTS price_ratio_pct NUMERIC(10, 4);
                        ALTER TABLE gold.fct_elementary_indices ADD COLUMN IF NOT EXISTS elementary_index NUMERIC(10, 4);
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                    UPDATE gold.fct_elementary_indices
                    SET elementary_index = COALESCE(price_ratio_pct, ROUND(price_ratio * 100.0, 4))
                    WHERE elementary_index IS NULL;
                """)

                # 1. Upsert Elementary Indices
                if not elementary_df.empty:
                    calc_dt = elementary_df["calculation_date"].iloc[0]
                    cur.execute(
                        "DELETE FROM gold.fct_elementary_indices WHERE calculation_date = %s AND (elementary_index > 300.0 OR elementary_index < 33.0);",
                        (calc_dt,)
                    )

                elem_rows = [
                    (
                        r.calculation_date, str(r.item_id), r.coicop_division, r.coicop_code,
                        r.base_price_khr, r.current_price_khr, r.price_ratio, r.price_ratio_pct,
                        r.price_ratio_pct,
                        r.is_imputed, int(r.observation_count)
                    )
                    for r in elementary_df.itertuples(index=False)
                ]
                execute_batch(cur, """
                    INSERT INTO gold.fct_elementary_indices (
                        calculation_date, item_id, coicop_division, coicop_code,
                        base_price_khr, current_price_khr, price_ratio, price_ratio_pct,
                        elementary_index,
                        is_imputed, observation_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (calculation_date, item_id) DO UPDATE
                    SET coicop_division = EXCLUDED.coicop_division,
                        coicop_code = EXCLUDED.coicop_code,
                        base_price_khr = EXCLUDED.base_price_khr,
                        current_price_khr = EXCLUDED.current_price_khr,
                        price_ratio = EXCLUDED.price_ratio,
                        price_ratio_pct = EXCLUDED.price_ratio_pct,
                        elementary_index = EXCLUDED.elementary_index,
                        is_imputed = EXCLUDED.is_imputed,
                        observation_count = EXCLUDED.observation_count
                """, elem_rows, page_size=1000)

                # 2. Upsert Daily Division & Headline CPI
                cpi_rows = [
                    (
                        r.calculation_date, r.coicop_division, r.division_name, r.weight,
                        None if pd.isna(r.division_index) else float(r.division_index),
                        headline["headline_cpi"], headline["core_cpi"],
                        int(r.item_count), int(r.observation_count)
                    )
                    for r in df_div.itertuples(index=False)
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
                    CREATE INDEX IF NOT EXISTS idx_fct_cpi_monthly_month ON gold.fct_cpi_monthly (cpi_month);
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

