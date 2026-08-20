"""
tests/test_gemini_coicop_classifier.py
──────────────────────────────────────
Unit tests for the Gemini AI COICOP classifier (Prompt 5).
Uses a fake model + a SQLAlchemy sqlite engine (no network, no API key).
"""

import json
import uuid

import pytest
from sqlalchemy import create_engine, text

from pipeline import gemini_coicop_classifier as gcc


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeModel:
    """Stand-in for genai.GenerativeModel: maps names -> (code, confidence, reason)."""

    def __init__(self, mapping: dict):
        self.mapping = mapping
        self.calls = 0

    def generate_content(self, contents, system_instruction=None):
        self.calls += 1
        names = contents if isinstance(contents, list) else [contents]
        arr = []
        for name in names:
            code, conf, reason = self.mapping.get(name, ("99.9.9", 0.0, "no match"))
            arr.append(
                {
                    "product_name": name,
                    "coicop_code": code,
                    "confidence_score": conf,
                    "reasoning": reason,
                }
            )
        return FakeResponse(json.dumps(arr))


class RaisingModel(FakeModel):
    def generate_content(self, contents, system_instruction=None):
        self.calls += 1
        raise RuntimeError("boom")


def _sqlite_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS silver"))
        conn.execute(text("ATTACH DATABASE ':memory:' AS staging"))
        conn.execute(
            text(
                "CREATE TABLE silver.dim_canonical_products ("
                "canonical_item_id TEXT PRIMARY KEY, canonical_name TEXT, "
                "coicop_code TEXT, classification_method TEXT, confidence_score REAL, "
                "needs_review INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE staging.stg_item_mapping ("
                "canonical_item_id TEXT, raw_item_id TEXT, raw_product_name TEXT, "
                "scrape_date TEXT, coicop_code TEXT, classification_method TEXT, "
                "confidence_score REAL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE silver.dim_coicop_ai_cache ("
                "product_name TEXT PRIMARY KEY, coicop_code TEXT, confidence_score REAL, "
                "reasoning TEXT, model_version TEXT, classified_at TEXT)"
            )
        )
    return engine


def _seed_item(engine, table, cid, name, coicop="99.9.9"):
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {table} (canonical_item_id, canonical_name, coicop_code, is_active) "
                "VALUES (:id, :name, :coicop, 1)"
            ),
            {"id": cid, "name": name, "coicop": coicop},
        )


def _seed_mapping(engine, cid, rid, name, date="2026-08-18"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO staging.stg_item_mapping "
                "(canonical_item_id, raw_item_id, raw_product_name, scrape_date, coicop_code) "
                "VALUES (:cid, :rid, :name, :date, NULL)"
            ),
            {"cid": cid, "rid": rid, "name": name, "date": date},
        )


# ── Unit-level ────────────────────────────────────────────────────────────────


def test_normalize_name():
    assert gcc._normalize_name("  Fresh   Milk 1L ") == "fresh milk 1l"


def test_parse_json_array_plain():
    raw = '[{"product_name": "Milk", "coicop_code": "01.1.4", "confidence_score": 0.98, "reasoning": "dairy"}]'
    parsed = gcc._parse_json_array(raw)
    assert parsed[0]["coicop_code"] == "01.1.4"


def test_parse_json_array_with_markdown_fence():
    raw = '```json\n[{"product_name": "Milk", "coicop_code": "01.1.4"}]\n```'
    parsed = gcc._parse_json_array(raw)
    assert parsed[0]["product_name"] == "Milk"


def test_parse_json_array_invalid_raises():
    with pytest.raises((json.JSONDecodeError, ValueError)):
        gcc._parse_json_array("not json")


def test_classify_batch_with_fake_model():
    model = FakeModel({"Milk": ("01.1.4", 0.98, "dairy product")})
    results = gcc.classify_batch(model, ["Milk"])
    assert results[0]["coicop_code"] == "01.1.4"
    assert model.calls == 1


def test_classify_names_batches_and_cache_hits():
    model = FakeModel(
        {
            "Milk 1L": ("01.1.4", 0.98, "dairy"),
            "Smartphone": ("08.2.0", 0.95, "phone"),
            "Bread": ("01.1.1", 0.9, "cereal"),
        }
    )
    cache = {
        gcc._normalize_name("Detergent"): {
            "product_name": "Detergent",
            "coicop_code": "05.6.1",
            "confidence_score": 0.9,
            "reasoning": "cached",
        }
    }
    outcome = gcc.classify_names(
        ["Milk 1L", "Smartphone", "Bread", "Detergent"],
        model=model,
        cache=cache,
        batch_size=2,
    )
    assert outcome["cache_hits"] == 1
    assert outcome["api_calls"] == 2  # 3 uncached names split into 2 + 1
    assert outcome["failed"] == 0
    assert outcome["results"]["Detergent"]["coicop_code"] == "05.6.1"
    assert outcome["results"]["Milk 1L"]["coicop_code"] == "01.1.4"


def test_classify_names_failed_batch_stays_unclassified():
    model = RaisingModel({})
    outcome = gcc.classify_names(["Milk"], model=model, batch_size=2)
    assert outcome["failed"] == 1
    assert outcome["results"]["Milk"]["coicop_code"] == "99.9.9"


# ── Integration-style (sqlite + fake model) ──────────────────────────────────


def test_classify_unclassified_with_gemini_end_to_end():
    engine = _sqlite_engine()
    model = FakeModel(
        {
            "Fresh Whole Milk 1L": ("01.1.4", 0.98, "whole milk"),
            "Smartphone Galaxy 8GB": ("08.2.0", 0.95, "handset"),
            "Organic Bananas": ("99.9.9", 0.40, "ambiguous produce"),
        }
    )

    items = [
        ("Fresh Whole Milk 1L", "R-MILK"),
        ("Smartphone Galaxy 8GB", "R-PHONE"),
        ("Organic Bananas", "R-BANANA"),
        ("Detergent 2kg", "R-DET"),
    ]
    for name, rid in items:
        cid = str(uuid.uuid4())
        _seed_item(engine, "silver.dim_canonical_products", cid, name)
        _seed_mapping(engine, cid, rid, name)

    # Pre-cached name: no API call for Detergent 2kg.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO silver.dim_coicop_ai_cache "
                "(product_name, coicop_code, confidence_score, reasoning, model_version) "
                "VALUES ('Detergent 2kg', '05.6.1', 0.9, 'household goods', 'test')"
            )
        )

    result = gcc.classify_unclassified_with_gemini(engine=engine, model=model)
    assert result["status"] == "OK"
    assert result["candidates"] == 4
    assert result["cache_hits"] == 1
    assert result["api_calls"] == 1  # 3 uncached names in one 50-batch

    with engine.connect() as conn:
        dims = conn.execute(
            text(
                "SELECT canonical_name, coicop_code FROM silver.dim_canonical_products"
            )
        ).fetchall()
        mappings = conn.execute(
            text(
                "SELECT raw_product_name, coicop_code, classification_method, confidence_score "
                "FROM staging.stg_item_mapping"
            )
        ).fetchall()
        cache_rows = conn.execute(
            text("SELECT product_name, coicop_code FROM silver.dim_coicop_ai_cache")
        ).fetchall()

    dim_by_name = {r[0]: r[1] for r in dims}
    assert dim_by_name["Fresh Whole Milk 1L"] == "01.1.4"
    assert dim_by_name["Smartphone Galaxy 8GB"] == "08.2.0"
    assert dim_by_name["Organic Bananas"] == "99.9.9"  # unclassified stays
    assert dim_by_name["Detergent 2kg"] == "05.6.1"  # from cache

    map_by_name = {r[0]: r for r in mappings}
    assert map_by_name["Fresh Whole Milk 1L"][1] == "01.1.4"
    assert map_by_name["Fresh Whole Milk 1L"][2] == "gemini_ai"
    assert map_by_name["Smartphone Galaxy 8GB"][2] == "gemini_ai"
    # 99.9.9 never persisted to the mapping
    assert map_by_name["Organic Bananas"][1] is None

    # Cache: classified names cached, unclassified '99.9.9' deliberately not.
    cache_names = {r[0] for r in cache_rows}
    assert "Fresh Whole Milk 1L" in cache_names
    assert "Organic Bananas" not in cache_names


def test_classify_unclassified_no_candidates():
    engine = _sqlite_engine()
    result = gcc.classify_unclassified_with_gemini(engine=engine, model=FakeModel({}))
    assert result["status"] == "SKIPPED_NO_UNCLASSIFIED"
    assert result["candidates"] == 0
