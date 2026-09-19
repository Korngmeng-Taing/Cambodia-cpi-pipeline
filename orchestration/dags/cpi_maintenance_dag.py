"""
orchestration/dags/cpi_maintenance_dag.py
─────────────────────────────────────────
Dedicated Maintenance & Partitioning Orchestration DAG for Cambodia CPI Pipeline.

Scheduled weekly (Sundays at 08:00 AM Phnom Penh time) or on manual trigger:
  1. Executes `ops.maintain_monthly_partitions(3)` to proactively ensure upcoming
     monthly partitions exist for bronze.raw_prices and silver.clean_store_prices.
  2. Runs table statistics updates (ANALYZE) on high-frequency tables.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

from pipeline.partition_manager import ensure_monthly_partitions

log = logging.getLogger(__name__)

DAG_ID = "cpi_maintenance_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


def _run_partition_maintenance(**context) -> dict:
    """Proactively ensures monthly partitions exist for 3 months ahead."""
    log.info("Starting scheduled partition maintenance...")
    result = ensure_monthly_partitions(months_ahead=3)
    log.info("Partition maintenance completed with result: %s", result)
    return result


def _run_cold_storage_offload(**context) -> dict:
    """Offloads completed historical monthly partitions to compressed columnar Parquet files."""
    from pipeline.cold_storage import run_cold_storage_offloading

    log.info("Starting scheduled cold storage Parquet offloading...")
    result = run_cold_storage_offloading(months_threshold=1, compression="zstd")
    log.info("Cold storage offloading completed with result: %s", result)
    return result


def _run_metabase_curation(**context) -> dict:
    """Curates Metabase catalog by hiding new partition tables and backend tables."""
    from pipeline.metabase_curator import curate_metabase_catalog

    log.info("Starting scheduled Metabase catalog curation...")
    result = curate_metabase_catalog()
    log.info("Metabase curation completed with result: %s", result)
    return result


def _run_table_vacuum_analyze(**context) -> None:
    """Refreshes statistics on high-turnover tables to optimize PostgreSQL query plans."""
    from pipeline.config import get_db_connection

    tables_to_analyze = [
        "staging.raw_scrapes",
        "bronze.raw_prices",
        "silver.clean_store_prices",
        "silver.canonical_items",
        "silver.dim_canonical_products",
        "silver.dim_coicop_ai_cache",
        "gold.dim_item_base_prices",
        "gold.fct_daily_prices",
        "gold.fct_elementary_indices",
        "gold.fct_cpi_daily",
    ]

    conn = get_db_connection()
    try:
        # Autocommit is required for VACUUM / ANALYZE in psycopg2
        conn.autocommit = True
        with conn.cursor() as cur:
            for tbl in tables_to_analyze:
                try:
                    log.info("Running ANALYZE on %s...", tbl)
                    cur.execute(f"ANALYZE {tbl};")
                except Exception as err:
                    log.warning("Could not run ANALYZE on %s: %s", tbl, err)
    finally:
        conn.close()


with DAG(
    dag_id=DAG_ID,
    description="Weekly Database & Table Partitioning Maintenance for Cambodia CPI Warehouse",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule="0 8 * * 0",  # Every Sunday at 08:00 AM Phnom Penh time
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["cpi", "maintenance", "partitioning", "postgres", "vacuum", "metabase"],
) as dag:

    start_task = EmptyOperator(task_id="start_maintenance")

    task_maintain_partitions = PythonOperator(
        task_id="maintain_monthly_partitions",
        python_callable=_run_partition_maintenance,
        execution_timeout=timedelta(minutes=10),
    )

    task_curate_metabase = PythonOperator(
        task_id="curate_metabase_catalog",
        python_callable=_run_metabase_curation,
        execution_timeout=timedelta(minutes=5),
    )

    task_offload_cold_storage = PythonOperator(
        task_id="offload_cold_storage_parquet",
        python_callable=_run_cold_storage_offload,
        execution_timeout=timedelta(minutes=20),
    )

    task_analyze_tables = PythonOperator(
        task_id="analyze_warehouse_tables",
        python_callable=_run_table_vacuum_analyze,
        execution_timeout=timedelta(minutes=15),
    )

    end_task = EmptyOperator(task_id="maintenance_complete")

    (
        start_task
        >> task_maintain_partitions
        >> task_curate_metabase
        >> task_offload_cold_storage
        >> task_analyze_tables
        >> end_task
    )
