"""
cleanup_dead_dags.py
────────────────────
Removes DAGs that no longer have source files from the Airflow metadata database.

Deletes all DagRuns, TaskInstances, XComs, Logs, reschedules and the DagModel rows for the
listed legacy DAG IDs so they stop appearing in the UI / API.

Usage (inside the airflow container):
    docker compose exec airflow-webserver python /opt/airflow/config/cleanup_dead_dags.py
"""

from airflow.models import (
    DagModel,
    DagRun,
    Log,
    RenderedTaskInstanceFields,
    TaskInstance,
    TaskReschedule,
    XCom,
)
from airflow.models.serialized_dag import SerializedDagModel
from airflow.utils.session import create_session

DEAD_DAG_IDS = [
    "cpi_medallion_pipeline_dag",  # old monolithic master (replaced by cpi_master_dag + per-source DAGs)
    "foodpanda_dag",  # replaced by bayonBKK_dag (Foodpanda restaurant scrape)
    "AeonMall_dag",  # replaced by aeon3_dag
    "eaon_misc_dag",  # typo'd / superseded aeon DAG
    "myphsar_dag",  # scraper removed
    "spark_cpi_analytics_dag",  # superseded by spark_etl_dag (ran with wrong image, no pyspark)
    "spark_etl_dag",  # superseded by silver_dag (no _SUCCESS sensors, lower retries)
]


def cleanup_dead_dags():
    print("Connecting to Airflow metadata database...")
    with create_session() as session:
        for dag_id in DEAD_DAG_IDS:
            dag_model = (
                session.query(DagModel).filter(DagModel.dag_id == dag_id).first()
            )
            if dag_model is None:
                print(f"  - {dag_id}: not present, skipping")
                continue

            session.query(DagRun).filter(DagRun.dag_id == dag_id).delete(
                synchronize_session=False
            )
            session.query(TaskInstance).filter(TaskInstance.dag_id == dag_id).delete(
                synchronize_session=False
            )
            session.query(XCom).filter(XCom.dag_id == dag_id).delete(
                synchronize_session=False
            )
            session.query(Log).filter(Log.dag_id == dag_id).delete(
                synchronize_session=False
            )

            try:
                session.query(SerializedDagModel).filter(
                    SerializedDagModel.dag_id == dag_id
                ).delete(synchronize_session=False)
            except Exception:
                pass

            try:
                session.query(TaskReschedule).filter(
                    TaskReschedule.dag_id == dag_id
                ).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                session.query(RenderedTaskInstanceFields).filter(
                    RenderedTaskInstanceFields.dag_id == dag_id
                ).delete(synchronize_session=False)
            except Exception:
                pass

            session.delete(dag_model)
            print(f"  - {dag_id}: removed (runs, task instances, xcoms, logs, model)")

        session.commit()
        print("Cleanup complete.")


if __name__ == "__main__":
    cleanup_dead_dags()
