"""
orchestration/dags/coicop_classification_dag.py
────────────────────────────────────────────────
Runs the Gemini AI COICOP classifier for products still flagged '99.9.9'
in the Silver layer.

    task: gemini_classify_unclassified

The rule-based keyword/regex classification happens in dbt
(stg_coicop_mapping, stg_rule_based_classification); this DAG mops up whatever
the rules left unclassified using Gemini (JSON mode) for the stragglers.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from pipeline.gemini_coicop_classifier import classify_unclassified_with_gemini

log = logging.getLogger(__name__)

local_tz = pendulum.timezone("Asia/Phnom_Penh")

DEFAULT_ARGS = {
    "owner": "cpi-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
    "execution_timeout": timedelta(minutes=30),
}


def _gemini_classify_callable(**context) -> dict:
    return classify_unclassified_with_gemini(scrape_date=context["ds"])


with DAG(
    dag_id="coicop_classification_dag",
    description="Gemini AI classification of unclassified (99.9.9) canonical products",
    start_date=pendulum.datetime(2024, 1, 1, tz=local_tz),
    schedule=None,  # Orchestrated strictly by cpi_master_dag
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["coicop", "gemini", "classification", "silver", "cpi"],
    max_active_runs=1,
) as dag:

    gemini_classify_unclassified = PythonOperator(
        task_id="gemini_classify_unclassified",
        python_callable=_gemini_classify_callable,
        execution_timeout=timedelta(minutes=30),
    )
