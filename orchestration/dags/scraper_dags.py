"""
orchestration/dags/scraper_dags.py
──────────────────────────────────
Per-source Daily Scraper DAGs — one DAG per source in SCRAPER_REGISTRY.

Each DAG implements the guide's Bronze ingestion path:
    fetch_records ─► canonical.normalize (Schema v1.0) ─► zero-product gate
      ─► PostgreSQL staging.raw_scrapes + bronze.raw_prices
      ─► bronze_dq_gate (verifies non-empty staging row)

DAG ids:  scrape_{source_slug}_dag   (e.g. scrape_aeon_dag, scrape_delishop_dag)
Schedule: None — triggered by cpi_master_dag at 02:00 daily (also runnable standalone).
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from pipeline.bronze_ingestion import check_bronze_gate, ingest_source_bronze
from scrapers.sources import SCRAPER_REGISTRY

log = logging.getLogger(__name__)

local_tz = pendulum.timezone("Asia/Phnom_Penh")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}


def _ingest_callable(source_slug: str, **context) -> dict:
    ds = context["ds"]
    log.info("Bronze ingestion for '%s' on %s", source_slug, ds)
    result = ingest_source_bronze(source_slug, ds)
    log.info("Ingested '%s' on %s: %s", source_slug, ds, result)
    return result


def _dq_gate_callable(source_slug: str, **context) -> int:
    ds = context["ds"]
    count = check_bronze_gate(source_slug, ds)
    log.info("Bronze gate OK for '%s' on %s: %d records", source_slug, ds, count)
    return count


def _build_scraper_dag(source_slug: str, dag_id: str | None = None):
    effective_dag_id = dag_id or f"scrape_{source_slug}_dag"
    with DAG(
        dag_id=effective_dag_id,
        description=f"Daily scrape & Bronze ingestion for {source_slug}",
        start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
        schedule=None,  # orchestrated by cpi_master_dag at 06:00
        catchup=False,
        default_args=DEFAULT_ARGS,
        tags=["bronze", "scraper", source_slug, "cpi"],
        max_active_runs=1,
    ) as dag:

        t_ingest = PythonOperator(
            task_id="scrape_ingest_bronze",
            python_callable=_ingest_callable,
            op_kwargs={"source_slug": source_slug},
        )
        t_gate = PythonOperator(
            task_id="bronze_dq_gate",
            python_callable=_dq_gate_callable,
            op_kwargs={"source_slug": source_slug},
        )

        t_ingest >> t_gate

    return dag


# Create exactly one standard DAG per source in the registry (20 DAGs total)
for _source_slug in SCRAPER_REGISTRY.keys():
    globals()[f"scrape_{_source_slug}_dag"] = _build_scraper_dag(_source_slug)
