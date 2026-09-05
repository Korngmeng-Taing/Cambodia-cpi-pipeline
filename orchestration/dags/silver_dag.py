"""
orchestration/dags/silver_dag.py
────────────────────────────────
Silver Layer DAG — transforms Bronze staging records into Silver clean
observations (item matching + hybrid vector embeddings + dbt).

Workflow:
    silver_item_matching_service ─► dbt_seed ─► [gemini_coicop_classification (non-blocking),
                                                hedonic_quality_adjustment]
      ─► dbt_silver_run ─► dbt_silver_test

Schedule: None — orchestrated by cpi_master_dag after all scraper DAGs finish.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from pipeline.gemini_coicop_classifier import classify_unclassified_with_gemini
from pipeline.gemini_item_reviewer import auto_review_pending_items
from pipeline.hedonic_regression import run_hedonic_regression
from pipeline.item_matcher import ItemMatcher
from pipeline.key_pool import get_key_pool


log = logging.getLogger(__name__)

DAG_ID = "silver_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")
DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry": False,
}


def _run_item_matching(**context) -> dict:
    dag_run_conf = context.get("dag_run").conf or {} if context.get("dag_run") else {}
    ds = dag_run_conf.get("ds") or context["ds"]
    log.info("Executing Silver Item Matching service (Vector + RapidFuzz + Spec Guard) for %s", ds)
    matcher = ItemMatcher()
    matched_stats = matcher.process_unmatched_batch(limit=100000, scrape_date=ds)
    log.info("ItemMatcher mapped batch stats: %s", matched_stats)
    return matched_stats


def _run_item_auto_review(**context) -> dict:
    """Executes Gemini AI + deterministic rule guards on pending item match reviews."""
    log.info("Executing Gemini AI Item Match Auto-Reviewer on silver.needs_review...")
    pool = get_key_pool()
    stats = auto_review_pending_items(
        limit=20000,
        use_rules_only=(pool.get_key_count() == 0),
    )
    log.info("Gemini Item Match Reviewer completed: %s", stats)
    return stats


def _safe_run_item_auto_review(**context) -> dict:
    """Graceful-degradation wrapper around Gemini item match reviewer."""
    try:
        return _run_item_auto_review(**context)
    except Exception as e:  # noqa: BLE001 - AI review must never block the Silver layer
        log.warning("Gemini item auto-review encountered error (non-blocking): %s", e)
        raise AirflowSkipException(f"Item auto-review skipped: {e}") from e


def _run_coicop_ai_classification(**context) -> dict:
    dag_run_conf = context.get("dag_run").conf or {} if context.get("dag_run") else {}
    ds = dag_run_conf.get("ds") or context["ds"]
    log.info("Executing Hybrid Vector & Gemini AI COICOP Classification for %s", ds)
    res = classify_unclassified_with_gemini(scrape_date=ds)
    log.info("COICOP AI Classification stats: %s", res)
    return res


def _safe_run_gemini(**context) -> dict:
    """Graceful-degradation wrapper around the Gemini COICOP classifier."""
    pool = get_key_pool()
    if pool.get_key_count() == 0 and not os.getenv("GEMINI_API_KEY"):
        log.warning(
            "No Gemini API keys detected — running vector/rule ladder only without external Gemini AI."
        )
        raise AirflowSkipException("No Gemini API keys configured.")
    try:
        return _run_coicop_ai_classification(**context)
    except Exception as e:  # noqa: BLE001 - AI must never block the Silver layer
        log.warning("Gemini classification failed (non-blocking): %s", e)
        raise AirflowSkipException(f"Gemini classification skipped: {e}") from e


def _run_hedonic_adjustment(**context) -> dict:
    dag_run_conf = context.get("dag_run").conf or {} if context.get("dag_run") else {}
    ds = dag_run_conf.get("ds") or context["ds"]
    log.info("Executing Log-Linear Hedonic Quality Adjustment for %s", ds)
    try:
        res = run_hedonic_regression(scrape_date=ds)
        log.info("Hedonic Regression stats: %s", res)
        return res
    except Exception as e:
        log.warning("Hedonic regression skipped or encountered error: %s", e)
        raise AirflowSkipException(f"Hedonic regression skipped: {e}") from e


with DAG(
    dag_id=DAG_ID,
    description="Silver Layer ETL: Item Matching -> Vector & AI Item Review -> COICOP AI -> Hedonic -> dbt Incremental (Bronze -> Silver)",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule=None,  # Orchestrated by cpi_master_dag
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["cpi", "silver", "dbt", "matching", "classification", "vectors"],
) as dag:

    # 1. Python Item Matching service
    task_item_matching = PythonOperator(
        task_id="silver_item_matching_service",
        python_callable=_run_item_matching,
    )

    # 2. Automated Item Review (Gemini Flash + Spec Guards on silver.needs_review)
    task_item_auto_review = PythonOperator(
        task_id="gemini_item_auto_review",
        python_callable=_safe_run_item_auto_review,
    )

    _dbt_flags = f"--project-dir {DBT_PROJECT_DIR} --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"

    # 3. Seed Reference Data
    task_dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"dbt seed {_dbt_flags} --full-refresh",
    )

    # 4. Hybrid Vector + Gemini COICOP Classification
    task_gemini_coicop = PythonOperator(
        task_id="gemini_coicop_classification",
        python_callable=_safe_run_gemini,
    )

    # 5. Hedonic Quality Adjustment
    task_hedonic_adjustment = PythonOperator(
        task_id="hedonic_quality_adjustment",
        python_callable=_run_hedonic_adjustment,
    )

    # 6. dbt Run
    dbt_ds_expr = '{{ (dag_run.conf.get("ds") if dag_run and dag_run.conf else None) or ds }}'
    _dbt_vars = f'{{"ds": "{dbt_ds_expr}"}}'
    task_dbt_silver_run = BashOperator(
        task_id="dbt_silver_run",
        trigger_rule="none_failed",
        bash_command=(
            f"dbt run {_dbt_flags} "
            "--select silver "
            f"--vars '{_dbt_vars}'"
        ),
    )

    # 7. dbt Test
    task_dbt_silver_test = BashOperator(
        task_id="dbt_silver_test",
        bash_command=(
            f"dbt test {_dbt_flags} "
            "--select silver"
        ),
    )

    # DAG Dependency Graph
    (
        task_item_matching
        >> task_item_auto_review
        >> task_dbt_seed
        >> task_dbt_silver_run
        >> task_gemini_coicop
        >> task_hedonic_adjustment
        >> task_dbt_silver_test
    )

