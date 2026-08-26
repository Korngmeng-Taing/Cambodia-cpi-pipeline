"""
orchestration/dags/cpi_master_dag.py
────────────────────────────────────
Master Orchestrator for the Cambodia CPI Medallion Pipeline.

Daily 07:00 Asia/Phnom_Penh (or manual trigger):
    Stage 1 (Bronze): Trigger all 20 per-source scraper DAGs in parallel.
    Stage 2 (Silver): Trigger silver_dag (Item matching + Gemini AI Classification + Log-Linear Hedonic + dbt Silver).
    Stage 3 (Gold):   Trigger gold_dag (dbt Gold star-schema models + tests).

NOTE: CPI index computation (Jevons / Laspeyres / GEKS / Fisher) is planned
but NOT implemented yet — Gold currently materializes the star schema only.

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
                SELECT count(DISTINCT store_slug)
                FROM staging.raw_scrapes
                WHERE scrape_date = %s::DATE AND record_count > 0;
                """,
                (ds,),
            )
            count = cur.fetchone()[0]
        log.info("Bronze layer success check for %s: %d store(s) with data", ds, count)
        if count < MIN_SUCCESSFUL_SCRAPERS:
            raise RuntimeError(
                f"Bronze failure: Only {count} store(s) succeeded for {ds} "
                f"(minimum required: {MIN_SUCCESSFUL_SCRAPERS}). Aborting Silver run."
            )
    finally:
        conn.close()


with DAG(
    dag_id=DAG_ID,
    description="Cambodia CPI Master Medallion Pipeline: Bronze (20 Scrapers) → Silver → COICOP AI → Gold",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule="0 7 * * *",  # Daily at 07:00 Phnom Penh time
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["cpi", "master", "medallion", "dbt", "production"],
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

    # Deliberately all_done: per-source scraper failures don't abort other scrapers,
    # but the minimum-success gate below ensures sufficient data exists.
    bronze_layer_complete = EmptyOperator(
        task_id="bronze_layer_complete",
        trigger_rule="all_done",
    )

    verify_bronze_gate = PythonOperator(
        task_id="verify_bronze_minimum_success",
        python_callable=_verify_minimum_scrapers_success,
        execution_timeout=timedelta(minutes=5),
    )

    trigger_silver = TriggerDagRunOperator(
        task_id="trigger_silver_dag",
        trigger_dag_id="silver_dag",
        conf={"scrape_date": "{{ ds }}"},
        wait_for_completion=True,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=SILVER_WAIT_TIMEOUT_SECONDS),
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

    gold_layer_complete = EmptyOperator(
        task_id="gold_layer_complete",
        trigger_rule="all_success",
    )

    cpi_pipeline_success = EmptyOperator(
        task_id="cpi_pipeline_success",
        trigger_rule="all_success",
    )

    # ── Strict Sequential Medallion Flow ──────────────────────────────────────
    start_cpi_pipeline >> trigger_scrapers >> bronze_layer_complete
    bronze_layer_complete >> verify_bronze_gate >> trigger_silver >> silver_layer_complete
    silver_layer_complete >> trigger_gold >> gold_layer_complete
    gold_layer_complete >> cpi_pipeline_success
