"""
=============================================================================
CAMBODIA DAILY CPI — GOLD LAYER CALCULATION DAG (03:30 AM ICT)
Triggers after Silver DAG completes:
  1. Computes Jevons micro-indices with 7-day missing price imputation.
  2. Aggregates 12 COICOP division indices with official NIS expenditure weights.
  3. Computes Headline CPI, Core CPI (ex-food & energy), and daily inflation.
  4. Dispatches failure / SLA alerts to Telegram & Slack.
=============================================================================
"""

import sys
import os
sys.path.insert(0, "/opt/airflow")

from datetime import datetime, timedelta, date
from airflow import DAG
from airflow.operators.python import PythonOperator
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

def execute_daily_cpi_calculation(**context):
    logical_date_str = context.get("ds")
    if logical_date_str:
        calc_date = datetime.strptime(logical_date_str, "%Y-%m-%d").date()
    else:
        calc_date = date.today()

    base_date = date(2026, 8, 18)
    print(f"🚀 Starting Gold CPI Calculation for {calc_date} (Base Date: {base_date})...")

    engine = CPICalculationEngine()
    engine.run_daily_pipeline(target_date=calc_date, base_date=base_date)
    print(f"✅ Gold CPI Calculation completed successfully for {calc_date}!")

with DAG(
    dag_id="gold_cpi_dag",
    default_args=DEFAULT_ARGS,
    description="Daily Jevons & Laspeyres CPI Economic Calculation Engine (03:30 AM ICT)",
    schedule_interval="30 3 * * *",
    start_date=datetime(2026, 8, 18),
    catchup=False,
    sla_miss_callback=airflow_sla_miss_callback,
    tags=["gold", "cpi", "inflation", "economics", "jevons", "laspeyres"],
) as dag:

    calculate_cpi_task = PythonOperator(
        task_id="calculate_daily_cpi_indices",
        python_callable=execute_daily_cpi_calculation,
        provide_context=True,
    )

    calculate_cpi_task
