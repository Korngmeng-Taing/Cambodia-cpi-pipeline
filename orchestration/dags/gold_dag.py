"""
orchestration/dags/gold_dag.py
──────────────────────────────
Gold Layer DAG — builds the Kimball Star Schema (Dimensions & Fact).

Workflow:
    dbt_gold_run (dim_items, dim_stores, fct_daily_prices)
      ─► dbt_gold_test

NOTE: CPI index computation (Jevons / Laspeyres / GEKS / Fisher) is planned
but NOT implemented yet — this DAG only materializes the star schema.

Schedule: None — orchestrated by cpi_master_dag after silver_dag finishes.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

log = logging.getLogger(__name__)

DAG_ID = "gold_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")
DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry": False,
}

from airflow.operators.python import PythonOperator


def _refresh_serving_views(**context):
    from pipeline.config import get_database_url
    import psycopg2

    sql_path = os.getenv("SQL_VIEWS_PATH", "/opt/airflow/sql/views.sql")
    if not os.path.exists(sql_path):
        sql_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "sql", "views.sql"
        )

    log.info("Applying serving views from %s", sql_path)
    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            views_sql = f.read()
    except FileNotFoundError:
        log.error("Views SQL file not found at %s", sql_path)
        raise

    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    try:
        with psycopg2.connect(conn_str) as conn:
            with conn.cursor() as cur:
                # Drop existing views first to handle column renames safely
                cur.execute("""
                    DO $$ DECLARE r RECORD;
                    BEGIN
                        FOR r IN SELECT schemaname, viewname FROM pg_views
                                 WHERE schemaname = 'gold'
                        LOOP
                            EXECUTE format('DROP VIEW IF EXISTS %I.%I', r.schemaname, r.viewname);
                        END LOOP;
                    END $$;
                """)
                cur.execute(views_sql)
            conn.commit()
        log.info("Successfully refreshed serving views in gold schema.")
    except Exception as exc:
        log.error("Failed to refresh serving views: %s", exc)
        raise


with DAG(
    dag_id=DAG_ID,
    description="Gold Layer ETL: Star Schema (Dims & Fact) -> dbt Tests -> Serving Views",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule=None,  # Orchestrated by cpi_master_dag
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["gold", "star-schema", "dbt", "cpi"],
) as dag:

    _dbt_vars = '{"ds": "{{ ds }}"}'
    _dbt_flags = f"--project-dir {DBT_PROJECT_DIR} --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"

    t_dbt_gold_run = BashOperator(
        task_id="dbt_gold_run",
        bash_command=f"dbt run --select gold --threads 4 {_dbt_flags} --vars '{_dbt_vars}'",
        execution_timeout=timedelta(minutes=30),
    )

    t_dbt_gold_test = BashOperator(
        task_id="dbt_gold_test",
        bash_command=f"dbt test --select gold --threads 4 {_dbt_flags}",
        execution_timeout=timedelta(minutes=15),
    )

    t_refresh_views = PythonOperator(
        task_id="refresh_serving_views",
        python_callable=_refresh_serving_views,
        execution_timeout=timedelta(minutes=5),
    )

    t_dbt_gold_run >> t_dbt_gold_test >> t_refresh_views
