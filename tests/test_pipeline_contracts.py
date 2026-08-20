"""
tests/test_pipeline_contracts.py
────────────────────────────────
Contract tests guarding the CPI math against regression. These verify that the
production index path (stored procedures + views + dbt models) implements the
methodology agreements:

  1. Headline Laspeyres REWEIGHTS official weights over present divisions
     (never divides by a fixed 100.0, which understated partial coverage).
  2. Elementary Jevons is unit-price-aware (per-kg/L where comparable).
  3. Base prices are bootstrapped idempotently (freeze semantics) in the DAG.
  4. GEKS multilateral (Layer 5) is wired into the orchestration.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SQL_DIR = PROJECT_ROOT / "sql"
DBT_MODELS = PROJECT_ROOT / "dbt" / "models"
DAGS = (
    PROJECT_ROOT / "orchestration" / "dags"
    if (PROJECT_ROOT / "orchestration" / "dags").exists()
    else PROJECT_ROOT / "dags"
)

GOLD_PROCEDURES = (SQL_DIR / "gold_procedures.sql").read_text(encoding="utf-8")
VIEWS_SQL = (SQL_DIR / "views.sql").read_text(encoding="utf-8")
FCT_GEVONS_DBT = (DBT_MODELS / "silver" / "fct_jevons_daily.sql").read_text(
    encoding="utf-8"
)
GOLD_DAG = (DAGS / "gold_dag.py").read_text(encoding="utf-8")


def test_headline_formula_is_reweighted_over_present():
    """CRITICAL-2 regression: production headline must renormalise weights to the
    divisions present, not divide by a fixed 100.0."""
    assert "weight_pct / NULLIF(v_total_weight, 0)" in GOLD_PROCEDURES
    # The old (incorrect) formulation must be gone from the stored procedure.
    assert "SUM(index_value * (weight_pct / 100.0))" not in GOLD_PROCEDURES


def test_category_index_joins_frozen_base_prices():
    """CRITICAL-1 regression: daily CPI must derive from frozen gold.base_prices."""
    assert "JOIN gold.base_prices b ON d.item_id = b.product_key" in GOLD_PROCEDURES


def test_base_prices_bootstrap_is_idempotent_and_wired():
    """CRITICAL-1 + MAJOR-5 regression: ensure-procedure exists and the DAG calls it."""
    assert "sp_ensure_base_prices" in GOLD_PROCEDURES
    assert "CALL gold.sp_ensure_base_prices" in GOLD_DAG
    assert "ensure_base_prices" in GOLD_DAG


def test_elementary_index_is_unit_price_aware():
    """MAJOR-4 regression: elementary Jevons uses per-kg/L unit prices where the
    item's quotes share a comparable base dimension, else falls back to shelf price."""
    for source in (GOLD_PROCEDURES, VIEWS_SQL, FCT_GEVONS_DBT):
        # Stored procedure qualifies columns with the `d.` alias; views/models do not,
        # and the dbt model uses lowercase `ln(...)`. Normalise for the checks.
        no_alias = source.replace("d.unit_price_khr", "unit_price_khr").replace(
            "d.price_khr", "price_khr"
        )
        upper = no_alias.upper()
        assert "unit_price_khr > 0" in source
        assert "LN(unit_price_khr)".upper() in upper
        assert "size_unit IN ('kg','g')".upper() in upper
        assert "size_unit IN ('l','ml')".upper() in upper
        assert "LN(price_khr)".upper() in upper  # shelf-price fallback preserved


def test_geks_is_wired_into_gold_dag():
    """CRITICAL-3 regression: GEKS-Törnqvist (Layer 5) must run in production."""
    assert "from pipeline.geks_calculator import GEKSCalculator" in GOLD_DAG
    assert "GEKSCalculator()" in GOLD_DAG
    assert "run_rolling_geks_for_date" in GOLD_DAG
    assert "geks_multilateral_calc" in GOLD_DAG
    # Daily rolling GEKS persists into the gold table.
    assert "run_rolling_geks_for_date" in (
        PROJECT_ROOT / "pipeline" / "geks_calculator.py"
    ).read_text(encoding="utf-8")


def test_observed_only_inflation_view_exists():
    """MAJOR-6 regression: DoD/MoM inflation must be computable on observed-only
    quotes (is_imputed = FALSE) so LOCF carry cannot smooth real price moves."""
    assert "v_inflation_observed" in VIEWS_SQL
    assert "WHERE is_imputed = FALSE" in VIEWS_SQL
