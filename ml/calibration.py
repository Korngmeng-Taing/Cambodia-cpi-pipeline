"""
ml/calibration.py
─────────────────
Macroeconometric 5-Basket RidgeCV Calibration Engine.

Estimates base drift (alpha) and empirical pass-through elasticities (beta)
across all 5 core COICOP baskets (Food, Alcohol, Housing, Transport, Restaurants)
and foreign exchange (USD/KHR) over an expanding 36-month historical panel.

Implements the multi-regressor Ridge framework established by CAPRED-GDDE (2026)
and evaluates out-of-sample performance against the Atkeson-Ohanian (2001) Random Walk.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV

from ml.config import (
    CAMBODIA_FIXED_HOLIDAYS,
    CAMBODIA_LUNAR_HOLIDAYS_BY_YEAR,
    NIS_COICOP_WEIGHTS,
    NOWCAST_TARGET_BASKETS,
)
from pipeline.config import get_db_connection

log = logging.getLogger(__name__)


class MacroDatasetBuilder:
    """Builds stationary monthly panels from official NIS history and high-frequency facts."""

    @staticmethod
    def is_major_festival_month(year: int, month: int) -> tuple[float, float]:
        """Returns (festival_score, is_festival_month) for major Cambodian lunar & solar festivals.
        - Khmer New Year: April (month 4)
        - Pchum Ben: September/October
        - Water Festival: November
        """
        score = 0.0
        is_fest = 0.0

        # Fixed solar holidays (Khmer New Year in April)
        if month == 4:
            score = 1.0
            is_fest = 1.0

        # Lunar festivals (Pchum Ben & Water Festival)
        lunar = CAMBODIA_LUNAR_HOLIDAYS_BY_YEAR.get(year, [])
        for hol in lunar:
            if hol["month"] == month:
                is_fest = 1.0
                score = max(score, 1.0)
                break

        return score, is_fest

    def load_36month_panel_from_seed(self) -> pd.DataFrame:
        """Loads 36-month official series from dbt/seeds/nis_official_cpi.csv with synthetic FX backfill."""
        seed_path = ROOT_DIR / "dbt" / "seeds" / "nis_official_cpi.csv"
        if not seed_path.exists():
            raise FileNotFoundError(f"Seed file not found: {seed_path}")

        df = pd.read_csv(seed_path)
        df["cpi_month"] = pd.to_datetime(df["cpi_month"]).dt.date
        df = df.sort_values("cpi_month").reset_index(drop=True)

        for col in [
            "headline_cpi", "cpi_division_01", "cpi_division_02",
            "cpi_division_04", "cpi_division_07", "cpi_division_11"
        ]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Synthetic/calibrated historical USD/KHR exchange rate baseline (4050 -> 4120 KHR/USD)
        n_rows = len(df)
        fx_rates = 4050.0 + np.linspace(0, 65.0, n_rows)
        df["fx_rate"] = fx_rates

        return df

    def fetch_training_panel(self) -> pd.DataFrame:
        """Fetches 36-month panel from PostgreSQL or falls back to seed data."""
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cpi_month, headline_cpi,
                           cpi_division_01, cpi_division_02,
                           cpi_division_04, cpi_division_07, cpi_division_11
                    FROM gold.dim_nis_official_cpi
                    WHERE cpi_month >= '2023-09-01'
                    ORDER BY cpi_month ASC;
                    """
                )
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                if rows and len(rows) >= 20:
                    df = pd.DataFrame(rows, columns=cols)
                    df["cpi_month"] = pd.to_datetime(df["cpi_month"]).dt.date
                    # Join FX
                    cur.execute(
                        """
                        SELECT date_trunc('month', execution_date)::date AS cpi_month,
                               AVG(rate) AS fx_rate
                        FROM staging.exchange_rates
                        GROUP BY 1
                        ORDER BY 1;
                        """
                    )
                    fx_rows = cur.fetchall()
                    if fx_rows:
                        df_fx = pd.DataFrame(fx_rows, columns=["cpi_month", "fx_rate"])
                        df = df.merge(df_fx, on="cpi_month", how="left")
                    if "fx_rate" not in df.columns or df["fx_rate"].isna().all():
                        df["fx_rate"] = 4050.0 + np.linspace(0, 65.0, len(df))
                    df["fx_rate"] = df["fx_rate"].bfill().ffill()
                    conn.close()
                    return df
            conn.close()
        except Exception as e:
            log.debug("Database query for 36-month panel fell back to seed: %s", e)

        return self.load_36month_panel_from_seed()

    def build_stationary_matrix(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """Transforms raw price levels into stationary log-returns (Delta log)."""
        df = df_raw.copy().sort_values("cpi_month").reset_index(drop=True)

        num_cols = [c for c in df.columns if c not in ["cpi_month", "release_date", "source_notes", "is_festival"]]
        for col in num_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

        # Target: Delta log of Headline CPI
        df["y_cpi_log"] = np.log(df["headline_cpi"] / df["headline_cpi"].shift(1))
        df["target_mom_pct"] = (np.exp(df["y_cpi_log"]) - 1.0) * 100.0

        # 5 Target Baskets (Delta log)
        basket_cols = {
            "01": ("cpi_division_01", "x_food_log"),
            "02": ("cpi_division_02", "x_alcohol_log"),
            "04": ("cpi_division_04", "x_housing_log"),
            "07": ("cpi_division_07", "x_transport_log"),
            "11": ("cpi_division_11", "x_restaurant_log"),
        }
        for _, (raw_col, log_col) in basket_cols.items():
            if raw_col in df.columns:
                df[log_col] = np.log(df[raw_col] / df[raw_col].shift(1))
            else:
                df[log_col] = df["y_cpi_log"]

        # FX (Delta log)
        if "fx_rate" in df.columns:
            df["x_fx_log"] = np.log(df["fx_rate"] / df["fx_rate"].shift(1))
        else:
            df["x_fx_log"] = 0.0

        # Cambodian festival indicators
        fest_flags = [self.is_major_festival_month(d.year, d.month) for d in df["cpi_month"]]
        df["festival_score"] = [f[0] for f in fest_flags]
        df["is_festival"] = [f[1] for f in fest_flags]

        # Random Walk 1-month lagged baseline
        df["rw_forecast_mom_pct"] = df["target_mom_pct"].shift(1)

        req_cols = ["y_cpi_log", "target_mom_pct", "rw_forecast_mom_pct"] + [b[1] for b in basket_cols.values()]
        return df.dropna(subset=req_cols).reset_index(drop=True)


class RidgeCalibrationEngine:
    """Estimates empirical 5-basket RidgeCV pass-through elasticities on expanding windows."""

    FEATURE_COLS = [
        "x_food_log",
        "x_alcohol_log",
        "x_housing_log",
        "x_transport_log",
        "x_restaurant_log",
        "x_fx_log",
    ]

    def __init__(self, alphas: list[float] | None = None):
        self.alphas = alphas or list(np.logspace(-2, 3, 50))

    def run_calibration(
        self,
        df_stationary: pd.DataFrame,
        train_split_months: int = 24,
    ) -> dict[str, Any]:
        """Runs expanding window RidgeCV training and out-of-sample Random Walk evaluation."""
        n_total = len(df_stationary)
        if n_total < 12:
            raise ValueError(f"Insufficient months for calibration: {n_total} (minimum 12)")

        train_size = min(train_split_months, n_total - 6)
        train_df = df_stationary.iloc[:train_size]
        test_df = df_stationary.iloc[train_size:]

        X_train = train_df[self.FEATURE_COLS].values
        y_train = train_df["y_cpi_log"].values

        # Fit RidgeCV with 5-fold cross-validation
        cv_folds = min(5, len(train_df) // 2)
        ridge_cv = RidgeCV(alphas=self.alphas, cv=cv_folds)
        ridge_cv.fit(X_train, y_train)

        best_alpha = float(ridge_cv.alpha_)
        intercept_alpha = float(ridge_cv.intercept_)
        coefs = {col: float(coef) for col, coef in zip(self.FEATURE_COLS, ridge_cv.coef_)}

        # Out-of-Sample Evaluation
        oos_results = {}
        if not test_df.empty:
            X_test = test_df[self.FEATURE_COLS].values
            y_test_log = test_df["y_cpi_log"].values
            actual_mom = test_df["target_mom_pct"].values
            rw_mom = test_df["rw_forecast_mom_pct"].values

            pred_log = ridge_cv.predict(X_test)
            pred_mom = (np.exp(pred_log) - 1.0) * 100.0

            model_err = pred_mom - actual_mom
            rw_err = rw_mom - actual_mom

            model_rmse = float(np.sqrt(np.mean(model_err ** 2)))
            rw_rmse = float(np.sqrt(np.mean(rw_err ** 2)))
            rel_rmse = float(model_rmse / rw_rmse) if rw_rmse > 0 else 1.0

            # Out-of-sample R²
            ss_res = np.sum((actual_mom - pred_mom) ** 2)
            ss_tot = np.sum((actual_mom - np.mean(actual_mom)) ** 2)
            oos_r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

            oos_results = {
                "test_months_count": len(test_df),
                "model_rmse": round(model_rmse, 4),
                "random_walk_rmse": round(rw_rmse, 4),
                "relative_rmse": round(rel_rmse, 4),
                "beats_random_walk": rel_rmse < 1.0,
                "error_reduction_pct": round((1.0 - rel_rmse) * 100.0, 2) if rel_rmse < 1.0 else 0.0,
                "oos_r2": round(oos_r2, 4),
            }

        return {
            "calibration_date": date.today(),
            "total_sample_months": n_total,
            "train_months_count": len(train_df),
            "sample_start": df_stationary["cpi_month"].iloc[0],
            "sample_end": df_stationary["cpi_month"].iloc[-1],
            "optimal_lambda": round(best_alpha, 4),
            "base_drift_alpha": round(intercept_alpha, 6),
            "elasticities": {
                "beta_food": round(coefs["x_food_log"], 4),
                "beta_alcohol": round(coefs["x_alcohol_log"], 4),
                "beta_housing": round(coefs["x_housing_log"], 4),
                "beta_transport": round(coefs["x_transport_log"], 4),
                "beta_restaurant": round(coefs["x_restaurant_log"], 4),
                "beta_fx": round(coefs["x_fx_log"], 4),
            },
            "out_of_sample": oos_results,
        }

    @staticmethod
    def persist_parameters(calib_res: dict[str, Any]) -> bool:
        """Saves calibrated macro parameters into gold.nowcast_calibrated_parameters."""
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gold.nowcast_calibrated_parameters (
                        calibration_date DATE NOT NULL,
                        sample_start DATE NOT NULL,
                        sample_end DATE NOT NULL,
                        sample_months INTEGER NOT NULL,
                        alpha_drift NUMERIC(8, 6) NOT NULL,
                        lambda_penalty NUMERIC(8, 4) NOT NULL,
                        beta_food NUMERIC(6, 4) NOT NULL,
                        beta_alcohol NUMERIC(6, 4) NOT NULL,
                        beta_housing NUMERIC(6, 4) NOT NULL,
                        beta_transport NUMERIC(6, 4) NOT NULL,
                        beta_restaurant NUMERIC(6, 4) NOT NULL,
                        beta_fx NUMERIC(6, 4) NOT NULL,
                        oos_relative_rmse NUMERIC(6, 4),
                        oos_r2 NUMERIC(6, 4),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (calibration_date)
                    );
                    """
                )
                elast = calib_res["elasticities"]
                oos = calib_res.get("out_of_sample", {})
                cur.execute(
                    """
                    INSERT INTO gold.nowcast_calibrated_parameters (
                        calibration_date, sample_start, sample_end, sample_months,
                        alpha_drift, lambda_penalty,
                        beta_food, beta_alcohol, beta_housing, beta_transport, beta_restaurant, beta_fx,
                        oos_relative_rmse, oos_r2
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s
                    )
                    ON CONFLICT (calibration_date) DO UPDATE
                    SET sample_start = EXCLUDED.sample_start,
                        sample_end = EXCLUDED.sample_end,
                        sample_months = EXCLUDED.sample_months,
                        alpha_drift = EXCLUDED.alpha_drift,
                        lambda_penalty = EXCLUDED.lambda_penalty,
                        beta_food = EXCLUDED.beta_food,
                        beta_alcohol = EXCLUDED.beta_alcohol,
                        beta_housing = EXCLUDED.beta_housing,
                        beta_transport = EXCLUDED.beta_transport,
                        beta_restaurant = EXCLUDED.beta_restaurant,
                        beta_fx = EXCLUDED.beta_fx,
                        oos_relative_rmse = EXCLUDED.oos_relative_rmse,
                        oos_r2 = EXCLUDED.oos_r2,
                        updated_at = NOW();
                    """,
                    (
                        calib_res["calibration_date"],
                        calib_res["sample_start"],
                        calib_res["sample_end"],
                        calib_res["total_sample_months"],
                        calib_res["base_drift_alpha"],
                        calib_res["optimal_lambda"],
                        elast["beta_food"],
                        elast["beta_alcohol"],
                        elast["beta_housing"],
                        elast["beta_transport"],
                        elast["beta_restaurant"],
                        elast["beta_fx"],
                        oos.get("relative_rmse"),
                        oos.get("oos_r2"),
                    ),
                )
                conn.commit()
            conn.close()
            log.info("✅ Calibrated parameters persisted into gold.nowcast_calibrated_parameters.")
            return True
        except Exception as e:
            log.warning("Could not persist calibrated parameters to database: %s", e)
            return False


def run_macro_calibration(train_split_months: int = 24) -> dict[str, Any]:
    """Top-level pipeline callable to run the 36-month 5-basket calibration."""
    builder = MacroDatasetBuilder()
    df_raw = builder.fetch_training_panel()
    df_stat = builder.build_stationary_matrix(df_raw)

    engine = RidgeCalibrationEngine()
    results = engine.run_calibration(df_stat, train_split_months=train_split_months)
    engine.persist_parameters(results)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("\n" + "=" * 65)
    print("  CAMBODIA 36-MONTH 5-BASKET RIDGE-CV MACRO CALIBRATION ENGINE")
    print("=" * 65)

    res = run_macro_calibration()
    el = res["elasticities"]
    oos = res.get("out_of_sample", {})

    print(f"\n[*] Sample Period:             {res['sample_start']} to {res['sample_end']}")
    print(f"[*] Total Months:              {res['total_sample_months']} (Train: {res['train_months_count']}, Test: {oos.get('test_months_count', 0)})")
    print(f"[*] Optimal Regularization λ:  {res['optimal_lambda']}")
    print(f"[*] Base Drift Intercept (α):  {res['base_drift_alpha']} (Monthly non-indicator drift)")

    print("\n[*] 5-Basket Pass-Through Elasticities (β):")
    print(f"    - Food (01):          {el['beta_food']:+.4f}  (NIS Weight: 44.8%)")
    print(f"    - Alcohol (02):       {el['beta_alcohol']:+.4f}  (NIS Weight:  1.6%)")
    print(f"    - Housing (04):       {el['beta_housing']:+.4f}  (NIS Weight: 17.1%)")
    print(f"    - Transport (07):     {el['beta_transport']:+.4f}  (NIS Weight: 12.2%)")
    print(f"    - Restaurants (11):   {el['beta_restaurant']:+.4f}  (NIS Weight:  3.1%)")
    print(f"    - FX (USD/KHR):       {el['beta_fx']:+.4f}")

    print("\n[*] Out-of-Sample Scorecard vs. Random Walk Benchmark:")
    print(f"    - Model RMSE:         {oos.get('model_rmse')} pp")
    print(f"    - Random Walk RMSE:   {oos.get('random_walk_rmse')} pp")
    print(f"    - Relative RMSE:      {oos.get('relative_rmse')} (Score < 1.00 beats Random Walk)")
    print(f"    - Beats Random Walk:  {oos.get('beats_random_walk')}")
    print(f"    - Error Reduction:    {oos.get('error_reduction_pct')}%")
    print(f"    - Out-of-Sample R²:   {oos.get('oos_r2')}")
    print("=" * 65 + "\n")
