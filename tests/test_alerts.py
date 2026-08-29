import pytest
try:
    from orchestration.dags.alerts import send_telegram_alert, send_slack_alert, airflow_task_failure_callback
except ImportError:
    from alerts import send_telegram_alert, send_slack_alert, airflow_task_failure_callback


def test_alerts_graceful_degradation_without_tokens(monkeypatch):
    # Ensure no tokens are configured
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")

    # Functions must return False gracefully without raising exceptions
    assert not send_telegram_alert("test message")
    assert not send_slack_alert("test message")


def test_airflow_task_failure_callback_runs_safely(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")

    class MockTaskInstance:
        task_id = "test_task"
        dag_id = "test_dag"
        log_url = "http://localhost:8085/log"

    context = {
        "task_instance": MockTaskInstance(),
        "exception": RuntimeError("Simulated test error"),
        "ds": "2026-08-26",
    }

    # Must execute safely without unhandled exceptions
    airflow_task_failure_callback(context)
