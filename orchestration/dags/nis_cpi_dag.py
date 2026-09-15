"""
orchestration/dags/nis_cpi_dag.py
───────────────────────────────────
Weekly Ground-Truth Ingestion DAG for Official NIS Cambodia Monthly CPI Releases.

Runs once a week (every Monday at 06:00 AM Asia/Phnom_Penh):
  1. Scrapes the NIS National CPI portal (https://nis.gov.kh/សន្ទស្សន៍ថ្នាក់ជាតិ/).
  2. Downloads any new or updated monthly Excel workbooks (CPI-12-group-*.xlsx).
  3. Ingests official headline, core, MoM, YoY, and all 12 COICOP division indices
     into gold.dim_nis_official_cpi and synchronizes dbt/seeds/nis_official_cpi.csv.
  4. Refreshes the gold tracking error model (fct_cpi_nis_comparison) via dbt.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.insert(0, "/opt/airflow")

log = logging.getLogger(__name__)

DAG_ID = "nis_cpi_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry": False,
}


def _scrape_and_ingest_nis_cpi() -> int:
    """Executes the automated NIS portal scraper and ingests official monthly releases."""
    from pipeline.nis_cpi_importer import NISBenchmarkImporter

    importer = NISBenchmarkImporter()
    discovered = importer.fetch_from_portal()
    log.info("NIS portal scraper completed. Ingested/verified %d monthly records.", len(discovered))
    return len(discovered)


def _refresh_nis_dbt_models() -> None:
    """Refreshes dbt seeds and the fct_cpi_nis_comparison tracking error model."""
    dbt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dbt")
    if not os.path.exists(dbt_dir):
        dbt_dir = "/opt/airflow/dbt"

    try:
        # Run dbt seed and run specifically for NIS models
        subprocess.run(
            ["dbt", "seed", "--select", "nis_official_cpi"],
            cwd=dbt_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        res = subprocess.run(
            ["dbt", "run", "--select", "fct_cpi_nis_comparison"],
            cwd=dbt_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        log.info("dbt run fct_cpi_nis_comparison output:\n%s", res.stdout)
    except Exception as exc:
        log.warning("dbt refresh skipped or encountered error (ignoring if dbt not on path): %s", exc)


with DAG(
    dag_id=DAG_ID,
    description="Weekly automated ingestion of official NIS Cambodia monthly CPI releases",
    schedule="0 8 * * 1",  # Every Monday at 08:00 AM ICT
    start_date=pendulum.datetime(2026, 1, 1, tz=local_tz),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["gold", "cpi", "nis", "benchmark", "weekly"],
    max_active_runs=1,
) as dag:
    scrape_task = PythonOperator(
        task_id="scrape_nis_portal",
        python_callable=_scrape_and_ingest_nis_cpi,
    )

    dbt_task = PythonOperator(
        task_id="refresh_nis_comparison_model",
        python_callable=_refresh_nis_dbt_models,
    )

    scrape_task >> dbt_task
