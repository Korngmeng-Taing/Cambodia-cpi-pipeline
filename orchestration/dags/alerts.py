"""
orchestration/dags/alerts.py
────────────────────────────
Unified Alerting & Notification Callbacks for Apache Airflow.
Supports Telegram Bot and Slack Webhook failure notifications with graceful degradation.
"""

from __future__ import annotations

import logging
import os
import requests
from typing import Any

log = logging.getLogger(__name__)

# Environment Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


def send_telegram_alert(message: str) -> bool:
    """Sends a formatted markdown message to Telegram channel/group."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.debug("Telegram alert skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        log.warning("Failed to send Telegram alert: %s", e)
        return False


def send_slack_alert(message: str) -> bool:
    """Sends a notification to a Slack webhook."""
    if not SLACK_WEBHOOK_URL:
        log.debug("Slack alert skipped: SLACK_WEBHOOK_URL not configured.")
        return False

    payload = {"text": message}
    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        log.warning("Failed to send Slack alert: %s", e)
        return False


def airflow_task_failure_callback(context: dict[str, Any]) -> None:
    """Standard Airflow on_failure_callback invoked when any task in any DAG fails."""
    ti = context.get("task_instance")
    dag = context.get("dag")
    exception = context.get("exception", "Unknown exception")
    execution_date = context.get("ds", "N/A")

    dag_id = dag.dag_id if dag else (ti.dag_id if ti else "Unknown_DAG")
    task_id = ti.task_id if ti else "Unknown_Task"
    log_url = ti.log_url if ti else ""

    alert_text = (
        f"🚨 *Airflow Task Failure Alert*\n\n"
        f"• *DAG:* `{dag_id}`\n"
        f"• *Task:* `{task_id}`\n"
        f"• *Date:* `{execution_date}`\n"
        f"• *Error:* `{str(exception)[:200]}`\n"
        f"• *Logs:* [View Task Logs]({log_url})"
    )

    log.error("Triggering Airflow failure alert for DAG: %s, Task: %s", dag_id, task_id)
    send_telegram_alert(alert_text)
    send_slack_alert(f":rotating_light: Airflow Task Failure in DAG `{dag_id}`, Task `{task_id}`: {str(exception)[:200]}")


def airflow_sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis) -> None:
    """Invoked when a DAG run exceeds its configured SLA time window."""
    dag_id = dag.dag_id if dag else "Unknown_DAG"
    alert_text = (
        f"⚠️ *Airflow SLA Miss Alert*\n\n"
        f"• *DAG:* `{dag_id}`\n"
        f"• *Tasks Missing SLA:* `{task_list}`\n"
        f"• *Blocking Tasks:* `{blocking_task_list}`\n"
    )
    log.warning("SLA miss detected for DAG: %s", dag_id)
    send_telegram_alert(alert_text)
    send_slack_alert(f":warning: SLA Miss in DAG `{dag_id}`")
