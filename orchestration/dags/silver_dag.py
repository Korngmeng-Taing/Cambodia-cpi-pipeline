"""
orchestration/dags/silver_dag.py
────────────────────────────────
Silver Layer DAG — transforms Bronze staging records into Silver clean
observations (item matching + hybrid vector embeddings + dbt).

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
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

try:
    from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig, RenderConfig, ExecutionConfig
    from cosmos.constants import ExecutionMode, LoadMode, TestBehavior
    HAS_COSMOS = True
except ImportError:
    HAS_COSMOS = False

from pipeline.gemini_item_reviewer import auto_review_pending_items
from pipeline.hedonic_regression import run_hedonic_regression
from pipeline.item_matcher import ItemMatcher
from pipeline.key_pool import get_key_pool


log = logging.getLogger(__name__)

DAG_ID = "silver_dag"
local_tz = pendulum.timezone("Asia/Phnom_Penh")
DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry": False,
}


def _run_item_matching(**context) -> dict:
    dag_run_conf = context.get("dag_run").conf or {} if context.get("dag_run") else {}
    ds = dag_run_conf.get("ds") or context["ds"]
    log.info("Executing Silver Item Matching service (Vector + RapidFuzz + Spec Guard) for %s", ds)
    try:
        matcher = ItemMatcher()
        matched_stats = matcher.process_unmatched_batch(limit=100000, scrape_date=ds)
        log.info("ItemMatcher mapped batch stats: %s", matched_stats)
        return matched_stats
    except Exception as err:
        log.error("Item matching service encountered fatal error for date %s: %s", ds, err, exc_info=True)
        raise


def _run_item_auto_review(**context) -> dict:
    """Executes Gemini AI + deterministic rule guards on pending item match reviews."""
    log.info("Executing Gemini AI Item Match Auto-Reviewer on silver.needs_review...")
    pool = get_key_pool()
    stats = auto_review_pending_items(
        limit=20000,
        use_rules_only=(pool.get_key_count() == 0),
    )
    log.info("Gemini Item Match Reviewer completed: %s", stats)
    return stats


def _safe_run_item_auto_review(**context) -> dict:
    """Graceful-degradation wrapper around Gemini item match reviewer."""
    try:
        return _run_item_auto_review(**context)
    except Exception as e:  # AI review must never block the Silver layer
        log.warning("Gemini item auto-review encountered error (non-blocking): %s", e)
        raise AirflowSkipException(f"Item auto-review skipped: {e}") from e


def _run_hedonic_adjustment(**context) -> dict:
    dag_run_conf = context.get("dag_run").conf or {} if context.get("dag_run") else {}
    ds = dag_run_conf.get("ds") or context["ds"]
    log.info("Executing Log-Linear Hedonic Quality Adjustment for %s", ds)
    try:
        res = run_hedonic_regression(scrape_date=ds)
        log.info("Hedonic Regression stats: %s", res)
        return res
    except Exception as e:
        log.warning("Hedonic regression skipped or encountered error: %s", e)
        raise AirflowSkipException(f"Hedonic regression skipped: {e}") from e


with DAG(
    dag_id=DAG_ID,
    description="Silver Layer ETL: Item Matching -> Vector & AI Item Review -> COICOP AI -> Hedonic -> dbt Incremental (Bronze -> Silver)",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule=None,  # Orchestrated by cpi_master_dag
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["cpi", "silver", "dbt", "matching", "classification", "vectors"],
) as dag:

    # 1. Python Item Matching service
    task_item_matching = PythonOperator(
        task_id="silver_item_matching_service",
        python_callable=_run_item_matching,
    )

    # 2. Automated Item Review (Gemini Flash + Spec Guards on silver.needs_review)
    task_item_auto_review = PythonOperator(
        task_id="gemini_item_auto_review",
        python_callable=_safe_run_item_auto_review,
    )

    _dbt_flags = f"--project-dir {DBT_PROJECT_DIR} --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"

    # 3. Seed Reference Data
    task_dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"dbt seed {_dbt_flags}",
    )

    # 4. Hybrid Hierarchical AI COICOP Classification (Llama 3.1 + Gemini Judge)
    task_gemini_coicop = BashOperator(
        task_id="gemini_coicop_classification",
        bash_command=f"export PYTHONPATH=. && python scripts/run_hierarchical_classification.py",
    )

    # 5. Hedonic Quality Adjustment
    task_hedonic_adjustment = PythonOperator(
        task_id="hedonic_quality_adjustment",
        python_callable=_run_hedonic_adjustment,
    )

    # 6. dbt Execution (Cosmos DbtTaskGroup if available, else BashOperator)
    dbt_ds_expr = '{{ (dag_run.conf.get("ds") if dag_run and dag_run.conf else None) or ds }}'
    _dbt_vars = f'{{"ds": "{dbt_ds_expr}"}}'

    # 3b. Stage int_prices_cleaned first so Gemini classification queries pre-cleaned indexed records
    task_dbt_stage_clean = BashOperator(
        task_id="dbt_stage_int_prices_cleaned",
        bash_command=(
            f"dbt run {_dbt_flags} "
            "--select int_prices_cleaned "
            f"--vars '{_dbt_vars}'"
        ),
    )

    if HAS_COSMOS:
        log.info("Astronomer Cosmos detected: instantiating DbtTaskGroup for Silver models.")
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
            select=["silver"],
            load_method=LoadMode.DBT_MANIFEST if has_manifest else LoadMode.AUTOMATIC,
            test_behavior=TestBehavior.AFTER_EACH,
        )
        cosmos_execution_config = ExecutionConfig(
            execution_mode=ExecutionMode.LOCAL,
        )
        tg_dbt_silver = DbtTaskGroup(
            group_id="dbt_silver",
            project_config=cosmos_project_config,
            profile_config=cosmos_profile_config,
            render_config=cosmos_render_config,
            execution_config=cosmos_execution_config,
        )

        task_join_silver_prep = EmptyOperator(
            task_id="silver_prep_completed",
            trigger_rule="none_failed_min_one_success",
        )

        task_item_matching >> task_dbt_stage_clean >> task_gemini_coicop >> task_join_silver_prep
        task_item_matching >> task_dbt_seed >> task_join_silver_prep
        task_item_matching >> task_item_auto_review >> task_join_silver_prep
        task_join_silver_prep >> tg_dbt_silver >> task_hedonic_adjustment
    else:
        log.info("Astronomer Cosmos not detected: falling back to BashOperator for Silver dbt.")
        task_join_silver_prep = EmptyOperator(
            task_id="silver_prep_completed",
            trigger_rule="none_failed_min_one_success",
        )

        task_dbt_silver_run = BashOperator(
            task_id="dbt_silver_run",
            bash_command=(
                f"dbt run {_dbt_flags} "
                "--select silver "
                f"--vars '{_dbt_vars}'"
            ),
        )

        task_dbt_silver_test = BashOperator(
            task_id="dbt_silver_test",
            bash_command=(
                f"dbt test {_dbt_flags} "
                "--select silver"
            ),
        )

        task_item_matching >> task_dbt_stage_clean >> task_gemini_coicop >> task_join_silver_prep
        task_item_matching >> task_dbt_seed >> task_join_silver_prep
        task_item_matching >> task_item_auto_review >> task_join_silver_prep
        task_join_silver_prep >> task_dbt_silver_run >> task_dbt_silver_test >> task_hedonic_adjustment

