"""
orchestration/dags/cpi_master_dag.py
────────────────────────────────────
Master Orchestrator for the Cambodia CPI Medallion Pipeline.

Daily 02:00 Asia/Phnom_Penh (or manual trigger):
    Stage 1 (Bronze): Trigger all per-source scraper DAGs in SCRAPER_REGISTRY in parallel.
    Stage 2 (Silver): Trigger silver_dag (Item matching + Vector & Gemini AI Classification + Log-Linear Hedonic + dbt Silver).
    Stage 3 (Gold CPI): Trigger gold_cpi_dag (Jevons elementary indices + 12-division Laspeyres + ML-Assisted Nowcasting + LightGBM Multi-Horizon Forecasting).
    Stage 4 (Gold Star): Trigger gold_dag (dbt Gold star-schema models + tests).

Visual & Execution Lineage:
    start ─► [All Registered Scrapers] ─► bronze_gate ─► silver_dag ─► gold_cpi_dag (Nowcast & Forecast)
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
WARNING_SCRAPERS_THRESHOLD = int(os.getenv("WARNING_SCRAPERS_THRESHOLD", "10"))


def _send_alert(subject: str, message: str, level: str = "warning") -> None:
    """Dispatches pipeline alerts to Slack and/or Telegram if configured."""
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    if slack_webhook:
        try:
            import requests
            emoji = "🚨" if level == "critical" else "⚠️"
            payload = {"text": f"{emoji} *[{level.upper()}] {subject}*\n{message}"}
            requests.post(slack_webhook, json=payload, timeout=10)
            log.info("Alert dispatched to Slack successfully.")
        except Exception as err:
            log.warning("Failed to dispatch Slack alert: %s", err)

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat_id:
        try:
            import requests
            emoji = "🚨" if level == "critical" else "⚠️"
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            payload = {
                "chat_id": telegram_chat_id,
                "text": f"{emoji} *[{level.upper()}] {subject}*\n{message}",
                "parse_mode": "Markdown",
            }
            requests.post(url, json=payload, timeout=10)
            log.info("Alert dispatched to Telegram successfully.")
        except Exception as err:
            log.warning("Failed to dispatch Telegram alert: %s", err)


def _verify_minimum_scrapers_success(**context) -> None:
    """Verifies that at least MIN_SUCCESSFUL_SCRAPERS succeeded in the current Bronze run.

    Sends automated Slack/Telegram warning alerts when fewer than WARNING_SCRAPERS_THRESHOLD
    (10) scrapers succeed, and aborts downstream pipeline if fewer than MIN_SUCCESSFUL_SCRAPERS (3).
    """
    from pipeline.config import get_db_connection
    from scrapers.sources import SCRAPER_REGISTRY

    dag_run_conf = context.get("dag_run").conf or {} if context.get("dag_run") else {}
    ds = (
        dag_run_conf.get("ds")
        or (
            context["data_interval_end"].in_timezone("Asia/Phnom_Penh").to_date_string()
            if "data_interval_end" in context
            else context["ds"]
        )
    )
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT store_slug, record_count
                FROM staging.raw_scrapes
                WHERE scrape_date = %s
                  AND record_count > 0
                """,
                (ds,),
            )
            rows = cur.fetchall()
            successful_stores = [r[0] for r in rows]
            successful = len(successful_stores)

        all_stores = set(SCRAPER_REGISTRY.keys())
        missing_stores = sorted(all_stores - set(successful_stores))

        log.info(
            "Bronze validation for %s: %d/%d distinct sources succeeded (minimum required: %d, warning threshold: %d)",
            ds,
            successful,
            len(all_stores),
            MIN_SUCCESSFUL_SCRAPERS,
            WARNING_SCRAPERS_THRESHOLD,
        )

        if successful < WARNING_SCRAPERS_THRESHOLD:
            msg = (
                f"Scraper intake degraded on *{ds}*: only {successful}/{len(all_stores)} sources succeeded.\n"
                f"• Successful: {', '.join(sorted(successful_stores)) or 'None'}\n"
                f"• Missing/Failed: {', '.join(missing_stores) or 'None'}"
            )
            level = "critical" if successful < MIN_SUCCESSFUL_SCRAPERS else "warning"
            log.warning("⚠️ %s", msg)
            _send_alert("Cambodia CPI Scraper Intake Warning", msg, level=level)

        if successful < MIN_SUCCESSFUL_SCRAPERS:
            raise RuntimeError(
                f"Bronze quality gate failed: only {successful} sources succeeded for {ds} "
                f"(minimum required: {MIN_SUCCESSFUL_SCRAPERS}). Aborting Silver/Gold pipeline."
            )
    finally:
        conn.close()


with DAG(
    dag_id=DAG_ID,
    description="Daily Cambodia CPI Master DAG: Fans out to all registered scrapers, then runs Silver and Gold layers sequentially.",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule="0 2 * * *",  # 02:00 AM Phnom Penh time daily
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["cpi", "master", "orchestration", "medallion", "monitoring"],
) as dag:

    start_task = EmptyOperator(task_id="start_pipeline")

    target_date_expr = "{{ (dag_run.conf.get('ds') if dag_run and dag_run.conf else None) or data_interval_end.in_timezone('Asia/Phnom_Penh').to_date_string() }}"

    # 1. Trigger all registered Scraper DAGs dynamically
    scraper_trigger_tasks = []
    for store_slug in sorted(SCRAPER_REGISTRY.keys()):
        trigger_op = TriggerDagRunOperator(
            task_id=f"trigger_scraper_{store_slug}",
            trigger_dag_id=f"scrape_{store_slug}_dag",
            conf={"ds": target_date_expr},
            wait_for_completion=True,
            deferrable=False,
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
        trigger_rule="all_done",
    )

    # 3. Trigger Silver DAG
    trigger_silver_task = TriggerDagRunOperator(
        task_id="trigger_silver_dag",
        trigger_dag_id="silver_dag",
        conf={"ds": target_date_expr},
        wait_for_completion=True,
        deferrable=False,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=SILVER_WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
        failed_states=["failed"],
    )

    # 4. Trigger Gold Economic CPI Calculation DAG (Jevons & Laspeyres)
    trigger_gold_cpi_task = TriggerDagRunOperator(
        task_id="trigger_gold_cpi_dag",
        trigger_dag_id="gold_cpi_dag",
        conf={"ds": target_date_expr},
        wait_for_completion=True,
        deferrable=False,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
        failed_states=["failed"],
    )

    # 5. Trigger Gold Star Schema DAG
    trigger_gold_task = TriggerDagRunOperator(
        task_id="trigger_gold_dag",
        trigger_dag_id="gold_dag",
        conf={"ds": target_date_expr},
        wait_for_completion=True,
        deferrable=False,
        poke_interval=WAIT_POKE_INTERVAL,
        execution_timeout=timedelta(seconds=WAIT_TIMEOUT_SECONDS),
        reset_dag_run=True,
        failed_states=["failed"],
    )

    end_task = EmptyOperator(task_id="cpi_pipeline_success")

    # Wire DAG dependencies
    start_task >> scraper_trigger_tasks >> bronze_gate_task >> trigger_silver_task >> trigger_gold_cpi_task >> trigger_gold_task >> end_task
