"""
pipeline/geks_calculator.py
───────────────────────────
Multilateral GEKS-Törnqvist Price Index Calculation Service.

Methodology:
- Computes bilateral Törnqvist price relatives across matched items for every pair of periods
  in a window (e.g. 13-month rolling window or daily rolling window).
- Computes the multilateral GEKS (Gini-Eltetö-Köves-Szulc) index:
    GEKS(t) = exp( 1/M * sum_j( ln T(j, t) ) - 1/M * sum_j( ln T(j, base) ) ) * 100
- Guarantees transitivity, circularity, and eliminates chain drift caused by product churn.
- Daily rolling GEKS anchors to the start of the rolling window (or specified period) to
  preserve transitivity across the active estimation window.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import psycopg2

log = logging.getLogger(__name__)


class GEKSCalculator:
    """
    Computes multilateral GEKS-Törnqvist price indices.
    """

    def __init__(self, db_conn_str: str | None = None):
        self.db_conn_str = db_conn_str or os.getenv(
            "CPI_DATABASE_URL",
            "postgresql://cpi_user:cpi_pass@localhost:5432/cpi_db",
        )

    def _get_connection(self):
        conn_str = self.db_conn_str.replace("postgresql+psycopg2://", "postgresql://")
        try:
            return psycopg2.connect(conn_str)
        except psycopg2.OperationalError:
            if "postgres" in conn_str:
                alt = conn_str.replace("postgres:5432", "localhost:5432")
            else:
                alt = conn_str.replace("localhost:5432", "postgres:5432")
            return psycopg2.connect(alt)

    @staticmethod
    def calculate_bilateral_tornqvist(
        prices_0: pd.Series,
        prices_1: pd.Series,
        weights_0: pd.Series | None = None,
        weights_1: pd.Series | None = None,
    ) -> tuple[float, int]:
        """
        Calculates the bilateral Törnqvist price index between period 0 and period 1
        over the intersection of matched items.

        Returns:
            (index_relative, matched_item_count) where index_relative = P_1 / P_0.
        """
        matched = prices_0.index.intersection(prices_1.index)
        matched = matched[(prices_0.loc[matched] > 0) & (prices_1.loc[matched] > 0)]

        n_matched = len(matched)
        if n_matched == 0:
            return 1.0, 0

        p0 = prices_0.loc[matched].values.astype(float)
        p1 = prices_1.loc[matched].values.astype(float)
        log_price_ratio = np.log(p1 / p0)

        if weights_0 is not None and weights_1 is not None:
            w0 = weights_0.reindex(matched).fillna(0).values.astype(float)
            w1 = weights_1.reindex(matched).fillna(0).values.astype(float)

            sum_w0 = np.sum(w0)
            sum_w1 = np.sum(w1)

            if sum_w0 > 0 and sum_w1 > 0:
                w0_norm = w0 / sum_w0
                w1_norm = w1 / sum_w1
                w_avg = 0.5 * (w0_norm + w1_norm)
                log_index = np.sum(w_avg * log_price_ratio)
                return float(np.exp(log_index)), n_matched

        # Unweighted geometric mean (Jevons-Törnqvist relative)
        log_index = np.mean(log_price_ratio)
        return float(np.exp(log_index)), n_matched

    def calculate_multilateral_geks(
        self,
        period_prices: dict[str, pd.Series],
        base_period: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Constructs the full bilateral matrix and calculates multilateral GEKS indices
        for all periods in the window.

        Returns:
            Dict of {period: {"index_value": float, "matched_count": int}}
        """
        periods = sorted(list(period_prices.keys()))
        m = len(periods)
        if m == 0:
            return {}

        if base_period is None or base_period not in periods:
            base_period = periods[0]

        # Construct bilateral ln(T) matrix
        log_matrix = np.zeros((m, m), dtype=float)
        matched_matrix = np.zeros((m, m), dtype=int)

        for i in range(m):
            for j in range(i, m):
                if i == j:
                    log_matrix[i, j] = 0.0
                    matched_matrix[i, j] = len(period_prices[periods[i]])
                else:
                    rel, n_match = self.calculate_bilateral_tornqvist(
                        period_prices[periods[i]],
                        period_prices[periods[j]],
                    )
                    log_matrix[i, j] = np.log(rel) if rel > 0 else 0.0
                    log_matrix[j, i] = -log_matrix[i, j]
                    matched_matrix[i, j] = n_match
                    matched_matrix[j, i] = n_match

        # GEKS log index for period k:
        # ln_GEKS(k) = (1/M) * sum_j log_matrix[j, k]
        geks_log_means = np.mean(log_matrix, axis=0)

        # Normalize relative to base_period
        base_idx = periods.index(base_period)
        base_log_mean = geks_log_means[base_idx]

        results = {}
        for idx, p in enumerate(periods):
            rel_log = geks_log_means[idx] - base_log_mean
            index_val = float(np.exp(rel_log) * 100.0)
            avg_matched = int(np.mean(matched_matrix[:, idx]))
            results[p] = {
                "index_value": round(index_val, 4),
                "matched_count": avg_matched,
            }

        return results

    def run_rolling_geks_for_date(
        self,
        target_date: str,
        window_size: int = 13,
        base_period: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Extracts observations for the window [target_date - (window_size - 1) days, target_date],
        computes multilateral GEKS index, and applies Movement Splicing to link into the
        historical continuous series without window base-drift (ILO & Eurostat standard).
        """
        dt_target = datetime.strptime(target_date, "%Y-%m-%d")
        dt_start = dt_target - timedelta(days=window_size - 1)
        start_date = dt_start.strftime("%Y-%m-%d")

        effective_base = base_period or start_date

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT scrape_date::TEXT, item_id, p_khr_jevons
                    FROM gold.fct_daily_price_stats
                    WHERE scrape_date >= %s::DATE AND scrape_date <= %s::DATE
                      AND p_khr_jevons > 0;
                    """,
                    (start_date, target_date),
                )
                rows = cur.fetchall()

            if not rows:
                log.warning("No price stats found for GEKS window %s to %s", start_date, target_date)
                return None

            df = pd.DataFrame(rows, columns=["scrape_date", "item_id", "p_khr_jevons"])
            period_dict: dict[str, pd.Series] = {}
            for d, grp in df.groupby("scrape_date"):
                period_dict[str(d)] = grp.set_index("item_id")["p_khr_jevons"].astype(float)

            geks_results = self.calculate_multilateral_geks(period_dict, base_period=effective_base)
            target_res = geks_results.get(target_date)
            if not target_res:
                return None

            # ── Movement Splice Linkage ──────────────────────────────────────────
            # Link period t to period t-1 using the price movement inside the current window
            sorted_periods = sorted(list(geks_results.keys()))
            target_idx = sorted_periods.index(target_date)
            final_index_value = target_res["index_value"]

            if target_idx > 0:
                prev_date = sorted_periods[target_idx - 1]
                prev_val_in_window = geks_results[prev_date]["index_value"]
                curr_val_in_window = target_res["index_value"]

                if prev_val_in_window > 0:
                    movement_ratio = curr_val_in_window / prev_val_in_window

                    # Fetch published continuous index for prev_date
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT index_value FROM gold.cpi_geks_multilateral
                            WHERE scrape_date = %s::DATE AND window_size = %s;
                            """,
                            (prev_date, window_size),
                        )
                        prev_row = cur.fetchone()

                    if prev_row:
                        final_index_value = round(float(prev_row[0]) * movement_ratio, 4)
                        log.info(
                            "Applied Movement Splice for %s: prev=%s (idx=%.4f) * ratio=%.4f -> %.4f",
                            target_date, prev_date, float(prev_row[0]), movement_ratio, final_index_value,
                        )

            # Upsert into gold.cpi_geks_multilateral
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gold.cpi_geks_multilateral (
                        scrape_date, base_period, window_size, formula, index_value, matched_items_count, calculated_at
                    ) VALUES (%s::DATE, %s, %s, 'GEKS-Törnqvist-Movement-Splice', %s, %s, NOW())
                    ON CONFLICT (scrape_date, base_period, window_size) DO UPDATE
                    SET index_value = EXCLUDED.index_value,
                        matched_items_count = EXCLUDED.matched_items_count,
                        calculated_at = NOW();
                    """,
                    (
                        target_date,
                        effective_base,
                        window_size,
                        final_index_value,
                        target_res["matched_count"],
                    ),
                )
            conn.commit()

            log.info(
                "Calculated Spliced GEKS for %s: index=%.4f (window=%d, base=%s, matched=%d)",
                target_date,
                final_index_value,
                window_size,
                effective_base,
                target_res["matched_count"],
            )
            return {
                "index_value": final_index_value,
                "matched_count": target_res["matched_count"],
            }

        finally:
            conn.close()

    def calculate_monthly_geks(
        self,
        target_month: str,
        window_months: int = 13,
        base_month: str = "2026-08",
    ) -> dict[str, Any] | None:
        """
        Computes standard monthly multilateral GEKS across a 13-month rolling window.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT TO_CHAR(scrape_date, 'YYYY-MM') as month_str, item_id,
                           ROUND(EXP(AVG(LN(p_khr_jevons))), 2) as p_khr_month
                    FROM gold.fct_daily_price_stats
                    WHERE scrape_date >= (TO_DATE(%s, 'YYYY-MM') - (INTERVAL '1 month' * (%s - 1)))::DATE
                      AND scrape_date < (TO_DATE(%s, 'YYYY-MM') + INTERVAL '1 month')::DATE
                      AND p_khr_jevons > 0
                    GROUP BY TO_CHAR(scrape_date, 'YYYY-MM'), item_id;
                    """,
                    (target_month, window_months, target_month),
                )
                rows = cur.fetchall()

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=["month_str", "item_id", "p_khr_month"])
            period_dict: dict[str, pd.Series] = {}
            for m, grp in df.groupby("month_str"):
                period_dict[str(m)] = grp.set_index("item_id")["p_khr_month"].astype(float)

            return self.calculate_multilateral_geks(period_dict, base_period=base_month)
        finally:
            conn.close()
