"""
orchestration/dags/cpi_master_dag.py
────────────────────────────────────
Master Orchestrator for the Cambodia CPI Medallion Pipeline.

Daily 02:00 Asia/Phnom_Penh (or manual trigger):
    Stage 1 (Bronze): Trigger all 20 per-source scraper DAGs in parallel.
    Stage 2 (Silver): Trigger silver_dag (Item matching + Vector & Gemini AI Classification + Log-Linear Hedonic + dbt Silver).
    Stage 3 (Gold):   Trigger gold_dag (dbt Gold star-schema models + tests).

Visual & Execution Lineage:
    start ─► [20 Scrapers] ─► bronze_complete ─► silver_dag ─► silver_complete
          ─► gold_dag ─► cpi_pipeline_success
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
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
SILVER_WAIT_TIMEOUT_SECONDS = 7200  # 2 hours for Silver layer
MIN_SUCCESSFUL_SCRAPERS = int(os.getenv("MIN_SUCCESSFUL_SCRAPERS", "3"))


def _verify_minimum_scrapers_success(**context) -> None:
    """Verifies that at least MIN_SUCCESSFUL_SCRAPERS succeeded in the current Bronze run.

    Prevents Silver and Gold from running on 100% empty/failed scrapes.
    """
    from pipeline.config import get_db_connection

    ds = context["ds"]
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT store_slug)
                FROM staging.raw_scrapes
                WHERE scrape_date = %s
                  AND record_count > 0
                """,
                (ds,),
            )
            row = cur.fetchone()
            successful = row[0] if row else 0

        log.info(
            "Bronze validation for %s: %d distinct sources succeeded (minimum required: %d)",
            ds,
            successful,
            MIN_SUCCESSFUL_SCRAPERS,
        )
        if successful < MIN_SUCCESSFUL_SCRAPERS:
            raise RuntimeError(
                f"Bronze quality gate failed: only {successful} sources succeeded for {ds} "
                f"(minimum required: {MIN_SUCCESSFUL_SCRAPERS}). Aborting Silver/Gold pipeline."
            )
    finally:
        conn.close()


with DAG(
    dag_id=DAG_ID,
    description="Daily Cambodia CPI Master DAG: Fans out to 20 scrapers, then runs Silver and Gold layers sequentially.",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule="0 2 * * *",  # 02:00 AM Phnom Penh time daily
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["cpi", "master", "orchestration", "medallion", "monitoring"],
) as dag:

    start_task = EmptyOperator(task_id="start_pipeline")

    # 1. Trigger all 20 Scraper DAGs dynamically
    scraper_trigger_tasks = []
    for store_slug in sorted(SCRAPER_REGISTRY.keys()):
        trigger_op = TriggerDagRunOperator(
            task_id=f"trigger_scraper_{store_slug}",
            trigger_dag_id=f"scrape_{store_slug}_dag",
            conf={"ds": "{{ ds }}"},
            wait_for_completion=True,
            poke_interval=WAIT_POKE_INTERVAL,
            execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
            reset_dag_run=True,
            failed_states=["failed"],
        )
        scraper_trigger_tasks.append(trigger_op)

    # 2. Gate check
    bronze_gate_task = PythonOperator(
        task_id="verify_bronze_quality_gate",
        python_callable=_verify_minimum_scrapers_success,
    )

    # 3. Trigger Silver DAG
    trigger_silver_task = TriggerDagRunOperator(
        task_id="trigger_silver_dag",
        trigger_dag_id="silver_dag",
        conf={"ds": "{{ ds }}"},
        wait_for_completion=True,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=SILVER_WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
        failed_states=["failed"],
    )

    # 4. Trigger Gold Star Schema DAG
    trigger_gold_task = TriggerDagRunOperator(
        task_id="trigger_gold_dag",
        trigger_dag_id="gold_dag",
        conf={"ds": "{{ ds }}"},
        wait_for_completion=True,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
        failed_states=["failed"],
    )

    # 5. Trigger Gold Economic CPI Calculation DAG (Jevons & Laspeyres)
    trigger_gold_cpi_task = TriggerDagRunOperator(
        task_id="trigger_gold_cpi_dag",
        trigger_dag_id="gold_cpi_dag",
        conf={"ds": "{{ ds }}"},
        wait_for_completion=True,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
        failed_states=["failed"],
    )

    end_task = EmptyOperator(task_id="cpi_pipeline_success")

    # Wire DAG dependencies
    start_task >> scraper_trigger_tasks >> bronze_gate_task >> trigger_silver_task >> trigger_gold_task >> trigger_gold_cpi_task >> end_task
