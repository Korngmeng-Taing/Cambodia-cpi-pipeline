"""
scripts/validate_environment.py
───────────────────────────────
Pre-flight environment and security configuration validator for the
Cambodia CPI Pipeline.

Validates:
  1. Cryptographic secret strength & default password guards (Fernet key, Webserver key, DB passwords).
  2. Database connectivity, user credentials, and required schemas (bronze, staging, silver, gold, ops).
  3. External API credentials (Google Gemini, Scraper tokens).
  4. Airflow orchestration prerequisites.

Exit Codes:
  0: All pre-flight checks passed.
  1: Critical security or configuration errors detected.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NamedTuple

# Ensure project root is on sys.path when executed directly as a script
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Default dev keys that MUST NOT be used in production
INSECURE_DEV_SECRETS: dict[str, str] = {
    "AIRFLOW__CORE__FERNET_KEY": "YlCImzjge_TeZc7jPJ7Jz2pgFJlFKMGFB7DkzCpjwBc=",
    "AIRFLOW__WEBSERVER__SECRET_KEY": "cpi_pipeline_airflow_secret_key_2026_secure",
    "CPI_DB_PASSWORD": "cpi_pass",
    "DB_PASS": "cpi_pass",
    "POSTGRES_PASSWORD": "postgres",
}

REQUIRED_SCHEMAS: tuple[str, ...] = ("bronze", "staging", "silver", "gold", "ops")


class ValidationIssue(NamedTuple):
    level: str  # "ERROR" or "WARNING"
    key: str
    message: str


def check_secrets(is_production: bool) -> list[ValidationIssue]:
    """Validates encryption keys and database passwords."""
    issues: list[ValidationIssue] = []

    for env_var, insecure_val in INSECURE_DEV_SECRETS.items():
        val = os.getenv(env_var, "")
        if val == insecure_val:
            msg = (
                f"Uses insecure default development credential: '{val}'. "
                "Must be rotated with a secure random secret."
            )
            if is_production:
                issues.append(ValidationIssue("ERROR", env_var, msg))
            else:
                issues.append(ValidationIssue("WARNING", env_var, msg))

    # Check Fernet Key validity (must be 44-char base64 urlsafe string)
    fernet = os.getenv("AIRFLOW__CORE__FERNET_KEY", "")
    if fernet and len(fernet) != 44:
        issues.append(
            ValidationIssue(
                "ERROR" if is_production else "WARNING",
                "AIRFLOW__CORE__FERNET_KEY",
                f"Invalid Fernet key length ({len(fernet)} chars). Must be 44 base64 characters.",
            )
        )

    # Check Webserver Secret Key
    web_secret = os.getenv("AIRFLOW__WEBSERVER__SECRET_KEY", "")
    if not web_secret:
        issues.append(
            ValidationIssue(
                "ERROR" if is_production else "WARNING",
                "AIRFLOW__WEBSERVER__SECRET_KEY",
                "Webserver secret key is empty.",
            )
        )
    elif len(web_secret) < 16:
        issues.append(
            ValidationIssue(
                "WARNING",
                "AIRFLOW__WEBSERVER__SECRET_KEY",
                "Secret key is shorter than 16 characters. Consider using a 32+ char random string.",
            )
        )

    return issues


def check_api_keys(is_production: bool) -> list[ValidationIssue]:
    """Validates third-party API keys and scraper tokens."""
    issues: list[ValidationIssue] = []

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS")
    if not gemini_key:
        issues.append(
            ValidationIssue(
                "WARNING",
                "GEMINI_API_KEY",
                "No Google Gemini API key configured. AI item classification and review will fall back to local rule-based matching.",
            )
        )

    vb_token = os.getenv("VIREAKBUNTHAM_BEARER_TOKEN")
    if not vb_token:
        issues.append(
            ValidationIssue(
                "WARNING",
                "VIREAKBUNTHAM_BEARER_TOKEN",
                "Vireak Buntham bearer token not set. Scraper may fall back to baseline static routes.",
            )
        )

    return issues


def check_database_connectivity() -> list[ValidationIssue]:
    """Attempts connection to PostgreSQL and verifies pipeline schemas."""
    issues: list[ValidationIssue] = []
    try:
        from pipeline.config import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.execute(
                    """
                    SELECT schema_name FROM information_schema.schemata
                    WHERE schema_name IN %s;
                    """,
                    (REQUIRED_SCHEMAS,),
                )
                existing_schemas = {r[0] for r in cur.fetchall()}
                missing = set(REQUIRED_SCHEMAS) - existing_schemas
                if missing:
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            "POSTGRES_SCHEMAS",
                            f"Missing required database schemas: {sorted(missing)}. Run postgres-init or migrations.",
                        )
                    )
        finally:
            conn.close()
    except Exception as exc:
        issues.append(
            ValidationIssue(
                "ERROR",
                "DATABASE_CONNECTION",
                f"Could not connect to PostgreSQL warehouse: {exc}",
            )
        )
    return issues


def validate_environment(
    is_production: bool = False,
    check_db: bool = True,
) -> tuple[bool, list[ValidationIssue]]:
    """Runs all environment checks and returns pass/fail status."""
    all_issues: list[ValidationIssue] = []
    all_issues.extend(check_secrets(is_production=is_production))
    all_issues.extend(check_api_keys(is_production=is_production))

    if check_db:
        all_issues.extend(check_database_connectivity())

    has_errors = any(issue.level == "ERROR" for issue in all_issues)
    return not has_errors, all_issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Cambodia CPI Pipeline Environment Pre-Flight Validator")
    parser.add_argument(
        "--prod",
        "--production",
        action="store_true",
        dest="production",
        default=os.getenv("ENVIRONMENT", "").lower() in ("production", "prod"),
        help="Enforce strict production security policies",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip database connection and schema checks",
    )
    args = parser.parse_args()

    mode_str = "PRODUCTION" if args.production else "DEVELOPMENT"
    print(f"\n{'='*65}")
    print(f"  CAMBODIA CPI PIPELINE — ENVIRONMENT PRE-FLIGHT [{mode_str}]")
    print(f"{'='*65}\n")

    passed, issues = validate_environment(
        is_production=args.production,
        check_db=not args.skip_db,
    )

    errors = [i for i in issues if i.level == "ERROR"]
    warnings = [i for i in issues if i.level == "WARNING"]

    if errors:
        print(f"[!] CRITICAL CONFIGURATION ERRORS ({len(errors)}):")
        for err in errors:
            print(f"   [{err.level}] {err.key}: {err.message}")
        print()

    if warnings:
        print(f"[*] CONFIG WARNINGS ({len(warnings)}):")
        for warn in warnings:
            print(f"   [{warn.level}] {warn.key}: {warn.message}")
        print()

    if passed and not warnings:
        print("[OK] All environment and security checks passed perfectly!\n")
        return 0
    elif passed:
        print("[OK] Environment is valid for execution (with warnings above).\n")
        return 0
    else:
        print("[FAIL] Environment validation failed. Resolve critical errors before proceeding.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
