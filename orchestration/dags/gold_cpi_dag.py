"""
=============================================================================
CAMBODIA DAILY CPI — GOLD LAYER CALCULATION DAG (03:30 AM ICT)
Triggers after Silver DAG completes:
  1. Computes Jevons micro-indices with 7-day missing price imputation.
  2. Aggregates 12 COICOP division indices with official NIS expenditure weights.
  3. Computes Headline CPI, Core CPI (ex-food & energy), and daily inflation.
  4. Dispatches failure / SLA alerts to Telegram & Slack.

REBASING POLICY (see docs/rebasing_policy.md):
  - Base period is the average of the preceding December (ILO CPI Manual §9.41).
  - Annual rebasing occurs on Jan 1 (or first business day) via the `annual_rebase_cpi`
    task. The new base_date is written to the Airflow Variable `cpi_base_date`.
  - The daily calculation always reads `cpi_base_date` (fallback: 2026-08-18).
=============================================================================
"""

import sys
import os
sys.path.insert(0, "/opt/airflow")

from datetime import datetime, timedelta, date
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
try:
    from orchestration.dags.alerts import airflow_task_failure_callback, airflow_sla_miss_callback
except ImportError:
    try:
        from dags.alerts import airflow_task_failure_callback, airflow_sla_miss_callback
    except ImportError:
        from alerts import airflow_task_failure_callback, airflow_sla_miss_callback

from pipeline.cpi_calculator import CPICalculationEngine

DEFAULT_ARGS = {
    "owner": "cpi-data-team",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "sla": timedelta(minutes=20),
    "on_failure_callback": airflow_task_failure_callback,
}

def get_base_date() -> date:
    """Fetch base date from Airflow Variable; fallback to project inception date."""
    try:
        base_str = Variable.get("cpi_base_date")
        return datetime.strptime(base_str, "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return date(2026, 8, 18)

def execute_daily_cpi_calculation(**context):
    logical_date_str = context.get("ds")
    if logical_date_str:
        calc_date = datetime.strptime(logical_date_str, "%Y-%m-%d").date()
    else:
        calc_date = date.today()

    base_date = get_base_date()
    print(f"🚀 Starting Gold CPI Calculation for {calc_date} (Base Date: {base_date})...")

    engine = CPICalculationEngine()
    engine.run_daily_pipeline(target_date=calc_date, base_date=base_date)
    print(f"✅ Gold CPI Calculation completed successfully for {calc_date}!")

def annual_rebase_cpi(**context):
    """
    Annual rebasing task: runs on Jan 1 (or first business day).
    Computes the average CPI for the preceding December and sets that as the new base.
    """
    logical_date_str = context.get("ds")
    if logical_date_str:
        run_date = datetime.strptime(logical_date_str, "%Y-%m-%d").date()
    else:
        run_date = date.today()

    # Only run in January
    if run_date.month != 1:
        print(f"⏭️ Skipping annual rebase: not January (current month: {run_date.month})")
        return

    # Determine preceding December
    dec_year = run_date.year - 1
    dec_start = date(dec_year, 12, 1)
    dec_end = date(dec_year, 12, 31)

    engine = CPICalculationEngine()
    df_dec = engine.load_clean_prices(dec_start, dec_end)

    if df_dec.empty:
        print(f"⚠️ No price data for December {dec_year}; rebasing skipped.")
        return

    # Compute average December headline CPI across all days with data
    dec_dates = df_dec["scrape_date"].unique()
    cpi_values = []
    for d in dec_dates:
        try:
            base_df = engine.compute_base_prices(d, df_dec)
            elem = engine.compute_daily_elementary_indices(d, base_df, df_dec)
            _, headline = engine.aggregate_division_and_headline(elem, d)
            cpi_values.append(headline["headline_cpi"])
        except Exception:
            continue

    if cpi_values:
        avg_cpi = sum(cpi_values) / len(cpi_values)
        # Set base to Dec 1 (the start of the averaging period)
        new_base = dec_start
        Variable.set("cpi_base_date", new_base.strftime("%Y-%m-%d"))
        print(f"✅ Annual rebasing complete: new base_date = {new_base} (avg December CPI: {avg_cpi:.2f})")
    else:
        print(f"⚠️ Could not compute December average CPI; rebasing skipped.")

local_tz = pendulum.timezone("Asia/Phnom_Penh")

with DAG(
    dag_id="gold_cpi_dag",
    default_args=DEFAULT_ARGS,
    description="Daily Jevons & Laspeyres CPI Economic Calculation Engine (triggered by cpi_master_dag)",
    schedule=None,  # Triggered by cpi_master_dag, not cron — avoids double execution
    start_date=pendulum.datetime(2026, 8, 18, tz=local_tz),
    catchup=False,
    sla_miss_callback=airflow_sla_miss_callback,
    tags=["gold", "cpi", "inflation", "economics", "jevons", "laspeyres"],
) as dag:

    calculate_cpi_task = PythonOperator(
        task_id="calculate_daily_cpi_indices",
        python_callable=execute_daily_cpi_calculation,
    )

    annual_rebase_task = PythonOperator(
        task_id="annual_rebase_cpi",
        python_callable=annual_rebase_cpi,
    )

    calculate_cpi_task >> annual_rebase_task
