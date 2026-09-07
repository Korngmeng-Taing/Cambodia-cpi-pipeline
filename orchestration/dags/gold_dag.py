"""
orchestration/dags/gold_dag.py
──────────────────────────────
Gold Layer DAG — builds the Kimball Star Schema (Dimensions & Fact).

Workflow:
    dbt_gold_run (dim_items, dim_stores, fct_daily_prices)
      ─► dbt_gold_test

NOTE: CPI index computation (Jevons elementary indices + Laspeyres division aggregation)
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
from airflow.operators.python import PythonOperator

try:
    from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig, RenderConfig, ExecutionConfig
    from cosmos.constants import ExecutionMode, LoadMode, TestBehavior
    HAS_COSMOS = True
except ImportError:
    HAS_COSMOS = False

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


def _refresh_serving_views(**context):
    from pipeline.config import get_db_connection

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

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # views.sql must use CREATE OR REPLACE VIEW — we no longer
                # drop all views first because that would destroy dbt-managed
                # views and any view added by future dbt models.
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
    tags=["gold", "star-schema", "dbt", "cpi", "cosmos"],
) as dag:

    dbt_ds_expr = '{{ (dag_run.conf.get("ds") if dag_run and dag_run.conf else None) or ds }}'
    _dbt_vars = f'{{"ds": "{dbt_ds_expr}"}}'
    _dbt_flags = f"--project-dir {DBT_PROJECT_DIR} --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"

    t_refresh_views = PythonOperator(
        task_id="refresh_serving_views",
        python_callable=_refresh_serving_views,
        execution_timeout=timedelta(minutes=5),
    )

    if HAS_COSMOS:
        log.info("Astronomer Cosmos detected: instantiating DbtTaskGroup for Gold models.")
        manifest_path = os.path.join(DBT_PROJECT_DIR, "target", "manifest.json")
        has_manifest = os.path.isfile(manifest_path)

        cosmos_profile_config = ProfileConfig(
            profile_name="cpi",
            target_name="cpi_target",
            profiles_yml_filepath=os.path.join(DBT_PROJECT_DIR, "profiles.yml"),
        )
        cosmos_project_config = ProjectConfig(
            dbt_project_path=DBT_PROJECT_DIR,
            manifest_path=manifest_path if has_manifest else None,
            dbt_vars={"ds": dbt_ds_expr},
            install_dbt_deps=False,
        )
        cosmos_render_config = RenderConfig(
            select=["gold"],
            load_method=LoadMode.DBT_MANIFEST if has_manifest else LoadMode.AUTOMATIC,
            test_behavior=TestBehavior.AFTER_EACH,
        )
        cosmos_execution_config = ExecutionConfig(
            execution_mode=ExecutionMode.LOCAL,
        )
        tg_dbt_gold = DbtTaskGroup(
            group_id="dbt_gold",
            project_config=cosmos_project_config,
            profile_config=cosmos_profile_config,
            render_config=cosmos_render_config,
            execution_config=cosmos_execution_config,
        )
        tg_dbt_gold >> t_refresh_views
    else:
        log.info("Astronomer Cosmos not detected: falling back to BashOperator for Gold dbt.")
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

        t_dbt_gold_run >> t_dbt_gold_test >> t_refresh_views
