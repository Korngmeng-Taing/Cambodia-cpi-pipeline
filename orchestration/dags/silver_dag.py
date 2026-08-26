"""
orchestration/dags/silver_dag.py
────────────────────────────────
Silver Layer DAG — transforms Bronze staging records into Silver clean
observations (item matching + dbt).

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
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from pipeline.gemini_coicop_classifier import classify_unclassified_with_gemini
from pipeline.gemini_item_reviewer import auto_review_pending_items
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
    matched_stats = matcher.process_unmatched_batch(limit=100000, scrape_date=ds)
    log.info("ItemMatcher mapped batch stats: %s", matched_stats)
    return matched_stats


def _run_item_auto_review(**context) -> dict:
    """Executes Gemini AI + deterministic rule guards on pending item match reviews."""
    log.info("Executing Gemini AI Item Match Auto-Reviewer on silver.needs_review...")
    stats = auto_review_pending_items(
        limit=20000,
        use_rules_only=not bool(os.getenv("GEMINI_API_KEY")),
    )
    log.info("Gemini Item Match Reviewer completed: %s", stats)
    return stats


def _safe_run_item_auto_review(**context) -> dict:
    """Graceful-degradation wrapper around Gemini item match reviewer."""
    try:
        return _run_item_auto_review(**context)
    except Exception as e:  # noqa: BLE001 - AI review must never block the Silver layer
        log.warning("Gemini item auto-review encountered error (non-blocking): %s", e)
        return {"status": "SKIPPED_ERROR", "error": str(e)}


def _run_coicop_ai_classification(**context) -> dict:
    ds = context["ds"]
    log.info("Executing Gemini AI COICOP Classification for %s", ds)
    res = classify_unclassified_with_gemini(scrape_date=ds)
    log.info("COICOP AI Classification stats: %s", res)
    return res


def _safe_run_gemini(**context) -> dict:
    """Graceful-degradation wrapper around the Gemini COICOP classifier.

    The rule ladder in int_coicop_classified.sql is the authoritative
    classifier — the AI step is a cache-warming optimization, never a
    hard dependency:
      - GEMINI_API_KEY missing  -> SKIPPED_NO_KEY (rule ladder only).
      - Any runtime failure     -> SKIPPED_ERROR (never fails Silver).
    """
    if not os.getenv("GEMINI_API_KEY"):
        log.warning(
            "GEMINI_API_KEY missing — skipping AI classification; rule ladder only."
        )
        return {"status": "SKIPPED_NO_KEY", "candidates": 0, "classified": 0}
    try:
        return _run_coicop_ai_classification(**context)
    except Exception as e:  # noqa: BLE001 - AI must never block the Silver layer
        log.warning("Gemini classification failed (non-blocking): %s", e)
        return {"status": "SKIPPED_ERROR", "error": str(e)}


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
    description="Silver Layer ETL: Item Matching -> AI Item Review -> COICOP AI -> Hedonic -> dbt Incremental (Bronze -> Silver)",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule=None,  # Orchestrated by cpi_master_dag
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["silver", "dbt", "rapidfuzz", "coicop", "gemini", "hedonic"],
) as dag:

    t_item_matching = PythonOperator(
        task_id="silver_item_matching_service",
        python_callable=_run_item_matching,
        execution_timeout=timedelta(minutes=45),
    )

    t_item_auto_review = PythonOperator(
        task_id="gemini_item_match_auto_reviewer",
        python_callable=_safe_run_item_auto_review,
        execution_timeout=timedelta(minutes=30),
        trigger_rule="all_done",
    )

    t_coicop_ai = PythonOperator(
        task_id="gemini_coicop_classification",
        python_callable=_safe_run_gemini,
        execution_timeout=timedelta(minutes=30),
        # all_done: run even if item matching upstream had issues, and the
        # callable itself never raises — a Gemini outage cannot fail Silver.
        trigger_rule="all_done",
    )

    t_hedonic = PythonOperator(
        task_id="hedonic_quality_adjustment",
        python_callable=_run_hedonic_adjustment,
        execution_timeout=timedelta(minutes=15),
    )

    _dbt_vars = '{"ds": "{{ ds }}"}'
    _dbt_flags = f"--project-dir {DBT_PROJECT_DIR} --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"
    # Idempotent: loads/refreshes dbt seeds (incl. coicop_classification_seed,
    # whose post-hook upserts bootstrap rows into silver.dim_coicop_ai_cache).
    # Runs BEFORE the AI step so seeded names never trigger Gemini API calls.
    t_dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"dbt seed {_dbt_flags}",
        execution_timeout=timedelta(minutes=15),
    )

    t_dbt_silver_run = BashOperator(
        task_id="dbt_silver_run",
        bash_command=f"dbt run --select silver --threads 4 {_dbt_flags} --vars '{_dbt_vars}'",
        execution_timeout=timedelta(minutes=30),
    )

    t_dbt_silver_test = BashOperator(
        task_id="dbt_silver_test",
        bash_command=f"dbt test --select silver --threads 4 {_dbt_flags}",
        execution_timeout=timedelta(minutes=15),
    )

    (
        t_item_matching
        >> t_item_auto_review
        >> t_dbt_seed
        >> [t_coicop_ai, t_hedonic]
        >> t_dbt_silver_run
        >> t_dbt_silver_test
    )

