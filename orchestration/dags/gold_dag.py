"""
orchestration/dags/gold_dag.py
──────────────────────────────
Gold Layer DAG — computes daily Elementary Jevons stats, 12 COICOP Category
indices, and Headline Laspeyres CPI for Cambodia CPI.

Workflow:
    calculate_daily_cpi_stored_proc ─► dbt_gold_run ─► dbt_gold_test

Schedule: None — orchestrated by cpi_master_dag after coicop_classification_dag.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from pipeline.config import get_db_connection
from pipeline.fisher_calculator import FisherCalculator
from pipeline.geks_calculator import GEKSCalculator

log = logging.getLogger(__name__)

DAG_ID = "gold_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")
DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}


def _ensure_base_prices(**context) -> None:
    """Idempotent base-price bootstrap. Freeze semantics: runs once per base period;
    gold.sp_ensure_base_prices skips when frozen rows already exist, so historical
    indices never shift from silent re-anchoring."""
    base_period = os.getenv("BASE_PERIOD", "2026-08")
    log.info("Ensuring base prices for base period %s", base_period)
    conn = get_db_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CALL gold.sp_ensure_base_prices(%s);", (base_period,))
    conn.close()
    log.info("Base prices ensured for %s", base_period)


def _run_gold_procedures(**context) -> None:
    ds = context["ds"]
    log.info("Calculating Daily Gold CPI for date: %s", ds)
    conn = get_db_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CALL gold.sp_calculate_daily_cpi(%s::DATE);", (ds,))
    conn.close()
    log.info("Successfully executed gold.sp_calculate_daily_cpi for %s", ds)


def _run_geks_multilateral(**context) -> dict:
    """Daily rolling GEKS (persisted) + best-effort monthly GEKS (logged).
    Layer 5 of the methodology: drift-free transitive index over a rolling window."""
    ds = context["ds"]
    base_period = os.getenv("BASE_PERIOD", "2026-08")
    calc = GEKSCalculator()
    daily = calc.run_rolling_geks_for_date(ds, window_size=13)
    if daily is None:
        log.warning("Daily rolling GEKS returned no result for %s (insufficient matched items)", ds)

    monthly = None
    try:
        month_results = calc.calculate_monthly_geks(ds[:7], window_months=13, base_month=base_period)
        monthly = (month_results or {}).get(ds[:7])
        if monthly is None:
            log.info("Monthly GEKS not yet available for %s (needs 13-month window)", ds[:7])
    except Exception as exc:  # noqa: BLE001 - monthly GEKS is diagnostic only
        log.warning("Monthly GEKS computation failed for %s: %s", ds[:7], exc)

    return {"daily": daily, "monthly": monthly}


def _run_fisher_superlative(**context) -> dict | None:
    """Calculates Superlative Fisher Ideal Index and Consumer Substitution Bias."""
    ds = context["ds"]
    base_period = os.getenv("BASE_PERIOD", "2026-08")
    calc = FisherCalculator()
    res = calc.run_fisher_for_date(ds, base_period=base_period)
    log.info("Fisher Superlative Index stats for %s: %s", ds, res)
    return res


with DAG(
    dag_id=DAG_ID,
    description="Gold Layer Aggregation: Stored Procedures + GEKS + Fisher + dbt Gold Models + Quality Tests",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule=None,  # Orchestrated by cpi_master_dag
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["gold", "cpi", "laspeyres", "jevons", "fisher", "geks", "dbt"],
) as dag:

    t_ensure_base_prices = PythonOperator(
        task_id="ensure_base_prices",
        python_callable=_ensure_base_prices,
    )

    t_calculate_cpi = PythonOperator(
        task_id="calculate_daily_cpi_procedure",
        python_callable=_run_gold_procedures,
    )

    t_geks_multilateral = PythonOperator(
        task_id="geks_multilateral_calc",
        python_callable=_run_geks_multilateral,
    )

    t_fisher_superlative = PythonOperator(
        task_id="fisher_superlative_calc",
        python_callable=_run_fisher_superlative,
    )

    _dbt_vars = '{"ds": "{{ ds }}"}'
    t_dbt_gold_run = BashOperator(
        task_id="dbt_gold_run",
        bash_command=f"dbt run --select gold --project-dir {DBT_PROJECT_DIR} --vars '{_dbt_vars}'",
        execution_timeout=timedelta(minutes=30),
    )

    t_dbt_gold_test = BashOperator(
        task_id="dbt_gold_test",
        bash_command=f"dbt test --select gold --project-dir {DBT_PROJECT_DIR}",
        execution_timeout=timedelta(minutes=15),
    )

    t_ensure_base_prices >> t_calculate_cpi >> [t_geks_multilateral, t_fisher_superlative] >> t_dbt_gold_run >> t_dbt_gold_test

