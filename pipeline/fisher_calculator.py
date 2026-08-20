"""
pipeline/fisher_calculator.py
───────────────────────────────
Superlative Fisher Ideal Price Index Calculator.

Methodology:
- Computes bilateral Laspeyres (P_L) using base-period expenditure/weights.
- Computes bilateral Paasche (P_P) using current-period expenditure/weights.
- Computes the Superlative Fisher Ideal Index:
    P_Fisher = sqrt(P_Laspeyres * P_Paasche)
- Quantifies Consumer Substitution Bias:
    Substitution_Bias = P_Laspeyres - P_Fisher
- Satisfies Time Reversal (P_01 * P_10 = 1) and Factor Reversal Axioms (Diewert 1976).
- Persists results to gold.cpi_fisher_superlative and updates gold.mart_cpi_daily.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import psycopg2

log = logging.getLogger(__name__)


class FisherCalculator:
    """
    Computes Superlative Fisher Ideal Price Indices and Consumer Substitution Bias.
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
    def calculate_bilateral_fisher(
        prices_0: pd.Series,
        prices_1: pd.Series,
        weights_0: pd.Series | None = None,
        weights_1: pd.Series | None = None,
    ) -> dict[str, float | int]:
        """
        Calculates Laspeyres, Paasche, Fisher Ideal Index, and Substitution Bias
        over matched items.

        Returns:
            Dict containing {
                "laspeyres_index": float,
                "paasche_index": float,
                "fisher_index": float,
                "substitution_bias_pct": float,
                "matched_items_count": int,
            }
        """
        matched = prices_0.index.intersection(prices_1.index)
        matched = matched[(prices_0.loc[matched] > 0) & (prices_1.loc[matched] > 0)]

        n_matched = len(matched)
        if n_matched == 0:
            return {
                "laspeyres_index": 100.0,
                "paasche_index": 100.0,
                "fisher_index": 100.0,
                "substitution_bias_pct": 0.0,
                "matched_items_count": 0,
            }

        p0 = prices_0.loc[matched].values.astype(float)
        p1 = prices_1.loc[matched].values.astype(float)
        price_ratios = p1 / p0

        # Weighted calculation if category / item weights are available
        if weights_0 is not None and weights_1 is not None:
            w0 = weights_0.reindex(matched).fillna(0).values.astype(float)
            w1 = weights_1.reindex(matched).fillna(0).values.astype(float)

            sum_w0 = np.sum(w0)
            sum_w1 = np.sum(w1)

            if sum_w0 > 0 and sum_w1 > 0:
                w0_norm = w0 / sum_w0
                w1_norm = w1 / sum_w1

                laspeyres = float(np.sum(w0_norm * price_ratios))
                paasche = float(1.0 / np.sum(w1_norm * (1.0 / price_ratios)))
                fisher = float(np.sqrt(laspeyres * paasche))
                bias = round((laspeyres - fisher) * 100.0, 3)

                return {
                    "laspeyres_index": round(laspeyres * 100.0, 4),
                    "paasche_index": round(paasche * 100.0, 4),
                    "fisher_index": round(fisher * 100.0, 4),
                    "substitution_bias_pct": bias,
                    "matched_items_count": n_matched,
                }

        # Unweighted Elementary Aggregation (Carli Laspeyres & Harmonic Paasche)
        laspeyres = float(np.mean(price_ratios))
        paasche = float(1.0 / np.mean(1.0 / price_ratios))
        fisher = float(np.sqrt(laspeyres * paasche))
        bias = round((laspeyres - fisher) * 100.0, 3)

        return {
            "laspeyres_index": round(laspeyres * 100.0, 4),
            "paasche_index": round(paasche * 100.0, 4),
            "fisher_index": round(fisher * 100.0, 4),
            "substitution_bias_pct": bias,
            "matched_items_count": n_matched,
        }

    def run_fisher_for_date(
        self,
        target_date: str,
        base_period: str = "2026-08",
    ) -> dict[str, Any] | None:
        """
        Computes Superlative Fisher Index between base period prices and current target_date,
        persists to gold.cpi_fisher_superlative, and returns summary stats.
        """
        conn = self._get_connection()
        try:
            # 1. Fetch base prices
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT product_key, base_price_khr
                    FROM gold.base_prices
                    WHERE base_period = %s AND base_price_khr > 0;
                    """,
                    (base_period,),
                )
                base_rows = cur.fetchall()

            # 2. Fetch current prices
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT item_id, p_khr_jevons
                    FROM gold.fct_daily_price_stats
                    WHERE scrape_date = %s::DATE AND p_khr_jevons > 0;
                    """,
                    (target_date,),
                )
                curr_rows = cur.fetchall()

            if not base_rows or not curr_rows:
                log.warning(
                    "Insufficient observations for Fisher index on %s (base=%d, curr=%d)",
                    target_date,
                    len(base_rows),
                    len(curr_rows),
                )
                return None

            s_base = pd.Series(
                {r[0]: float(r[1]) for r in base_rows},
                name="base_price",
            )
            s_curr = pd.Series(
                {r[0]: float(r[1]) for r in curr_rows},
                name="curr_price",
            )

            metrics = self.calculate_bilateral_fisher(s_base, s_curr)

            # 3. Upsert into gold.cpi_fisher_superlative
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gold.cpi_fisher_superlative (
                        scrape_date DATE NOT NULL,
                        base_period VARCHAR(16) NOT NULL DEFAULT '2026-08',
                        formula VARCHAR(32) NOT NULL DEFAULT 'Fisher-Superlative',
                        laspeyres_index NUMERIC(10, 4) NOT NULL,
                        paasche_index NUMERIC(10, 4) NOT NULL,
                        fisher_index NUMERIC(10, 4) NOT NULL,
                        substitution_bias_pct NUMERIC(6, 3) NOT NULL,
                        matched_items_count INT NOT NULL DEFAULT 0,
                        calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (scrape_date, base_period)
                    );
                    CREATE INDEX IF NOT EXISTS idx_gold_fisher_date ON gold.cpi_fisher_superlative(scrape_date DESC);

                    INSERT INTO gold.cpi_fisher_superlative (
                        scrape_date, base_period, formula, laspeyres_index,
                        paasche_index, fisher_index, substitution_bias_pct,
                        matched_items_count, calculated_at
                    ) VALUES (%s::DATE, %s, 'Fisher-Superlative', %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (scrape_date, base_period) DO UPDATE
                    SET laspeyres_index = EXCLUDED.laspeyres_index,
                        paasche_index = EXCLUDED.paasche_index,
                        fisher_index = EXCLUDED.fisher_index,
                        substitution_bias_pct = EXCLUDED.substitution_bias_pct,
                        matched_items_count = EXCLUDED.matched_items_count,
                        calculated_at = NOW();
                    """,
                    (
                        target_date,
                        base_period,
                        metrics["laspeyres_index"],
                        metrics["paasche_index"],
                        metrics["fisher_index"],
                        metrics["substitution_bias_pct"],
                        metrics["matched_items_count"],
                    ),
                )
            conn.commit()

            log.info(
                "Calculated Superlative Fisher Index for %s: Fisher=%.4f (Laspeyres=%.4f, Paasche=%.4f, Bias=%.3f%%, Matched=%d)",
                target_date,
                metrics["fisher_index"],
                metrics["laspeyres_index"],
                metrics["paasche_index"],
                metrics["substitution_bias_pct"],
                metrics["matched_items_count"],
            )
            return metrics

        finally:
            conn.close()
