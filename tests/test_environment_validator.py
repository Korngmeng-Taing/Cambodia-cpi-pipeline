"""
tests/test_environment_validator.py
───────────────────────────────────
Unit tests for the environment pre-flight validator (scripts/validate_environment.py).
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from scripts.validate_environment import (
    check_api_keys,
    check_database_connectivity,
    check_secrets,
    validate_environment,
)


def test_check_secrets_flags_insecure_keys_in_production(monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", "YlCImzjge_TeZc7jPJ7Jz2pgFJlFKMGFB7DkzCpjwBc=")
    monkeypatch.setenv("AIRFLOW__WEBSERVER__SECRET_KEY", "cpi_pipeline_airflow_secret_key_2026_secure")
    monkeypatch.setenv("CPI_DB_PASSWORD", "cpi_pass")

    issues = check_secrets(is_production=True)
    error_keys = {issue.key for issue in issues if issue.level == "ERROR"}

    assert "AIRFLOW__CORE__FERNET_KEY" in error_keys
    assert "AIRFLOW__WEBSERVER__SECRET_KEY" in error_keys
    assert "CPI_DB_PASSWORD" in error_keys


def test_check_secrets_reports_warnings_in_development(monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", "YlCImzjge_TeZc7jPJ7Jz2pgFJlFKMGFB7DkzCpjwBc=")
    monkeypatch.setenv("AIRFLOW__WEBSERVER__SECRET_KEY", "cpi_pipeline_airflow_secret_key_2026_secure")
    monkeypatch.setenv("CPI_DB_PASSWORD", "cpi_pass")

    issues = check_secrets(is_production=False)
    error_keys = {issue.key for issue in issues if issue.level == "ERROR"}
    warn_keys = {issue.key for issue in issues if issue.level == "WARNING"}

    assert len(error_keys) == 0, "No ERRORS should be emitted in development mode"
    assert "AIRFLOW__CORE__FERNET_KEY" in warn_keys
    assert "CPI_DB_PASSWORD" in warn_keys


def test_check_secrets_passes_with_strong_keys(monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", "0123456789012345678901234567890123456789012=")
    monkeypatch.setenv("AIRFLOW__WEBSERVER__SECRET_KEY", "super_strong_production_secret_key_32_chars!")
    monkeypatch.setenv("CPI_DB_PASSWORD", "StrongCustomProdPassw0rd_987#")
    monkeypatch.setenv("DB_PASS", "StrongCustomProdPassw0rd_987#")
    monkeypatch.setenv("POSTGRES_PASSWORD", "StrongCustomProdPassw0rd_987#")

    issues = check_secrets(is_production=True)
    error_keys = {issue.key for issue in issues if issue.level == "ERROR"}

    assert len(error_keys) == 0


def test_check_api_keys_warns_on_missing_gemini(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)

    issues = check_api_keys(is_production=True)
    warn_keys = {issue.key for issue in issues if issue.level == "WARNING"}

    assert "GEMINI_API_KEY" in warn_keys


def test_check_database_connectivity_verifies_schemas():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    # Mock schemas present
    mock_cur.fetchall.return_value = [("bronze",), ("staging",), ("silver",), ("gold",), ("ops",)]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("pipeline.config.get_db_connection", return_value=mock_conn):
        issues = check_database_connectivity()

    assert len(issues) == 0
    mock_conn.close.assert_called_once()


def test_check_database_connectivity_detects_missing_schemas():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    # Missing 'ops' and 'silver'
    mock_cur.fetchall.return_value = [("bronze",), ("staging",), ("gold",)]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("pipeline.config.get_db_connection", return_value=mock_conn):
        issues = check_database_connectivity()

    assert len(issues) == 1
    assert issues[0].level == "ERROR"
    assert "ops" in issues[0].message


def test_validate_environment_overall_flag(monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", "YlCImzjge_TeZc7jPJ7Jz2pgFJlFKMGFB7DkzCpjwBc=")
    # Production with default key must return passed=False
    passed, issues = validate_environment(is_production=True, check_db=False)
    assert passed is False
    assert any(i.level == "ERROR" for i in issues)

    # Dev with default key returns passed=True (only warnings)
    passed_dev, issues_dev = validate_environment(is_production=False, check_db=False)
    assert passed_dev is True
