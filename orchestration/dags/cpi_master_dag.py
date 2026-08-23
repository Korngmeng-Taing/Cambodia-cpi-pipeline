"""
orchestration/dags/cpi_master_dag.py
────────────────────────────────────
Master Orchestrator for the Cambodia CPI Medallion Pipeline.

Daily 07:00 Asia/Phnom_Penh (or manual trigger):
    Stage 1 (Bronze): Trigger all 20 per-source scraper DAGs in parallel.
    Stage 2 (Silver): Trigger silver_dag (Item matching + Gemini AI Classification + Log-Linear Hedonic + dbt Silver).
    Stage 3 (Gold):   Trigger gold_dag (Daily stored procedures + Spliced GEKS + dbt Gold models + tests).

Visual & Execution Lineage:
    start ─► [20 Scrapers] ─► bronze_complete ─► silver_dag ─► silver_complete
          ─► gold_dag ─► cpi_pipeline_success
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from scrapers.sources import SCRAPER_REGISTRY

log = logging.getLogger(__name__)

DAG_ID = "cpi_master_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}

WAIT_POKE_INTERVAL = 10
WAIT_TIMEOUT_SECONDS = 3600


with DAG(
    dag_id=DAG_ID,
    description="Cambodia CPI Master Medallion Pipeline: Bronze (20 Scrapers) → Silver → COICOP AI → Gold",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule="0 7 * * *",  # Daily at 07:00 Phnom Penh time
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["cpi", "master", "medallion", "dbt", "geks", "production"],
) as dag:

    start_cpi_pipeline = EmptyOperator(
        task_id="start_cpi_pipeline",
    )

    trigger_scrapers: list[TriggerDagRunOperator] = []
    for source_slug in SCRAPER_REGISTRY.keys():
        target_dag_id = f"scrape_{source_slug}_dag"

        trigger_scrapers.append(
            TriggerDagRunOperator(
                task_id=f"trigger_scrape_{source_slug}",
                trigger_dag_id=target_dag_id,
                conf={"scrape_date": "{{ ds }}"},
                wait_for_completion=True,
                poke_interval=WAIT_POKE_INTERVAL,
                execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
                reset_dag_run=True,
            )
        )

    # Deliberately all_done: a single scraper failure must not block the daily
    # index — silver/gold process whatever bronze produced. Failed sources stay
    # visible as failed trigger tasks in this run's graph.
    bronze_layer_complete = EmptyOperator(
        task_id="bronze_layer_complete",
        trigger_rule="all_done",
    )

    trigger_silver = TriggerDagRunOperator(
        task_id="trigger_silver_dag",
        trigger_dag_id="silver_dag",
        conf={"scrape_date": "{{ ds }}"},
        wait_for_completion=True,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
    )

    silver_layer_complete = EmptyOperator(
        task_id="silver_layer_complete",
        trigger_rule="all_success",
    )

    trigger_gold = TriggerDagRunOperator(
        task_id="trigger_gold_dag",
        trigger_dag_id="gold_dag",
        conf={"scrape_date": "{{ ds }}"},
        wait_for_completion=True,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
    )

    cpi_pipeline_success = EmptyOperator(
        task_id="cpi_pipeline_success",
        trigger_rule="all_success",
    )

    # ── Strict Sequential Medallion Flow ──────────────────────────────────────
    start_cpi_pipeline >> trigger_scrapers >> bronze_layer_complete
    bronze_layer_complete >> trigger_silver >> silver_layer_complete
    silver_layer_complete >> trigger_gold >> cpi_pipeline_success
