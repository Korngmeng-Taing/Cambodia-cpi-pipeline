"""
tests/test_dbt_unit_tests.py
─────────────────────────────
Validates the structural integrity and schema conformity of dbt 1.8+ unit tests.
"""

import os
import yaml

DBT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dbt")
SILVER_SCHEMA_PATH = os.path.join(DBT_DIR, "models", "silver", "schema.yml")
GOLD_SCHEMA_PATH = os.path.join(DBT_DIR, "models", "gold", "schema.yml")


def test_silver_schema_yaml_validity():
    """Ensure silver schema.yml parses cleanly without YAML errors."""
    assert os.path.exists(SILVER_SCHEMA_PATH), f"Schema file missing: {SILVER_SCHEMA_PATH}"
    with open(SILVER_SCHEMA_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    assert "unit_tests" in data, "unit_tests section must be present in silver schema.yml"


def test_silver_unit_tests_structure():
    """Ensure each unit test defines model, given, and expect blocks with rows."""
    with open(SILVER_SCHEMA_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    unit_tests = data.get("unit_tests", [])
    assert len(unit_tests) >= 3, f"Expected at least 3 unit tests, found {len(unit_tests)}"

    test_names = set()
    for ut in unit_tests:
        name = ut.get("name")
        assert name, "Unit test must have a name"
        assert name not in test_names, f"Duplicate unit test name: {name}"
        test_names.add(name)

        assert "model" in ut, f"Unit test {name} must declare target model"
        assert "given" in ut, f"Unit test {name} must declare given inputs"
        assert "expect" in ut, f"Unit test {name} must declare expect outputs"

        for given_item in ut["given"]:
            assert "input" in given_item, f"Given item missing input in {name}"
            assert "rows" in given_item, f"Given item missing rows in {name}"

        expect = ut["expect"]
        assert "rows" in expect, f"Expect section missing rows in {name}"
        assert len(expect["rows"]) > 0, f"Expect rows must not be empty in {name}"


def test_gold_schema_yaml_validity():
    """Ensure gold schema.yml parses cleanly without YAML errors."""
    assert os.path.exists(GOLD_SCHEMA_PATH), f"Schema file missing: {GOLD_SCHEMA_PATH}"
    with open(GOLD_SCHEMA_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    assert "unit_tests" in data, "unit_tests section must be present in gold schema.yml"


def test_gold_unit_tests_structure():
    """Ensure gold unit test defines model, given, and expect blocks with rows."""
    with open(GOLD_SCHEMA_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    unit_tests = data.get("unit_tests", [])
    assert len(unit_tests) >= 1, f"Expected at least 1 unit test, found {len(unit_tests)}"

    for ut in unit_tests:
        name = ut.get("name")
        assert name, "Unit test must have a name"
        assert "model" in ut, f"Unit test {name} must declare target model"
        assert "given" in ut, f"Unit test {name} must declare given inputs"
        assert "expect" in ut, f"Unit test {name} must declare expect outputs"

        for given_item in ut["given"]:
            assert "input" in given_item, f"Given item missing input in {name}"
            assert "rows" in given_item, f"Given item missing rows in {name}"

        expect = ut["expect"]
        assert "rows" in expect, f"Expect section missing rows in {name}"
        assert len(expect["rows"]) > 0, f"Expect rows must not be empty in {name}"

