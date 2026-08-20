"""
orchestration/dags/silver_dag.py
────────────────────────────────
Silver Layer DAG — transforms Bronze staging records into Silver clean
observations (item matching + dbt).

Workflow:
    silver_item_matching_service ─► dbt_silver_run ─► dbt_silver_test

Schedule: None — orchestrated by cpi_master_dag after all scraper DAGs finish.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from pipeline.gemini_coicop_classifier import classify_unclassified_with_gemini
from pipeline.hedonic_regression import run_hedonic_regression
from pipeline.item_matcher import ItemMatcher

log = logging.getLogger(__name__)

DAG_ID = "silver_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")
DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}


def _run_item_matching(**context) -> dict:
    ds = context["ds"]
    log.info("Executing Silver Item Matching service (RapidFuzz / Barcode) for %s", ds)
    matcher = ItemMatcher()
    matched_stats = matcher.process_unmatched_batch(limit=100000)
    log.info("ItemMatcher mapped batch stats: %s", matched_stats)
    return matched_stats


def _run_coicop_ai_classification(**context) -> dict:
    ds = context["ds"]
    log.info("Executing Gemini AI COICOP Classification for %s", ds)
    res = classify_unclassified_with_gemini(scrape_date=ds)
    log.info("COICOP AI Classification stats: %s", res)
    return res


def _run_hedonic_adjustment(**context) -> dict:
    ds = context["ds"]
    log.info("Executing Log-Linear Hedonic Quality Adjustment for %s", ds)
    try:
        res = run_hedonic_regression(scrape_date=ds)
        log.info("Hedonic Regression stats: %s", res)
        return res
    except Exception as e:
        log.warning("Hedonic regression skipped or encountered error: %s", e)
        return {"status": "SKIPPED", "error": str(e)}


with DAG(
    dag_id=DAG_ID,
    description="Silver Layer ETL: Item Matching -> COICOP AI -> Hedonic -> dbt Incremental (Bronze -> Silver)",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule=None,  # Orchestrated by cpi_master_dag
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["silver", "dbt", "rapidfuzz", "coicop", "gemini", "hedonic"],
) as dag:

    t_item_matching = PythonOperator(
        task_id="silver_item_matching_service",
        python_callable=_run_item_matching,
    )

    t_coicop_ai = PythonOperator(
        task_id="gemini_coicop_classification",
        python_callable=_run_coicop_ai_classification,
        execution_timeout=timedelta(minutes=30),
    )

    t_hedonic = PythonOperator(
        task_id="hedonic_quality_adjustment",
        python_callable=_run_hedonic_adjustment,
        execution_timeout=timedelta(minutes=15),
    )

    t_dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"dbt seed --project-dir {DBT_PROJECT_DIR}",
        execution_timeout=timedelta(minutes=10),
    )

    _dbt_vars = '{"ds": "{{ ds }}"}'
    t_dbt_silver_run = BashOperator(
        task_id="dbt_silver_run",
        bash_command=f"dbt run --select silver --project-dir {DBT_PROJECT_DIR} --vars '{_dbt_vars}'",
        execution_timeout=timedelta(minutes=30),
    )

    t_dbt_silver_test = BashOperator(
        task_id="dbt_silver_test",
        bash_command=f"dbt test --select silver --project-dir {DBT_PROJECT_DIR}",
        execution_timeout=timedelta(minutes=15),
    )

    t_item_matching >> t_coicop_ai >> t_hedonic >> t_dbt_seed >> t_dbt_silver_run >> t_dbt_silver_test
