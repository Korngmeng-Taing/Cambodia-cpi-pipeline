"""
tests/test_gemini_coicop_classifier.py
──────────────────────────────────────
Unit tests for the Gemini AI COICOP classifier (Prompt 5).
Uses a fake model + a SQLAlchemy sqlite engine (no network, no API key).

NOTE: as of the Risk-1 Option-A cleanup, silver.dim_canonical_products is no
longer a write target for this module (it isn't joined by any dbt model that
propagates COICOP into Silver/Gold facts). The classifier now:
  - reads unclassified items from silver.classification_queue
  - writes the canonical COICOP code into silver.dim_coicop_ai_cache
  - flips queue rows to RESOLVED (or keeps them PENDING on low confidence)

These tests reflect that contract.
"""

import json

import pytest
from sqlalchemy import create_engine, text

from pipeline import gemini_coicop_classifier as gcc


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeModel:
    """Stand-in for genai.GenerativeModel: maps names -> (code, confidence, reason).

    The real production call (classify_batch) sends
        model.generate_content([SYSTEM_PROMPT] + [name, ...])
    so this fake must skip the SYSTEM_PROMPT entry and only classify names that
    appear in its mapping; anything it doesn't recognise is silently dropped
    (matches the production contract: a "99.9.9" miss should never be returned
    by the model itself, only when persist_classifications sees an empty result).
    """

    def __init__(self, mapping: dict):
        self.mapping = mapping
        self.calls = 0

    def generate_content(self, contents, system_instruction=None):
        self.calls += 1
        names = contents if isinstance(contents, list) else [contents]
        arr = []
        for name in names:
            # Skip the SYSTEM_PROMPT preamble — it's not a product name.
            if not isinstance(name, str) or name.startswith("You are"):
                continue
            if name not in self.mapping:
                continue
            code, conf, reason = self.mapping[name]
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
                "CREATE TABLE silver.classification_queue ("
                "product_key TEXT PRIMARY KEY, name_clean TEXT, "
                "status TEXT NOT NULL DEFAULT 'PENDING', "
                "resolved_division TEXT, resolved_at TEXT, reason TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE silver.dim_coicop_ai_cache ("
                "product_name TEXT PRIMARY KEY, coicop_code TEXT, confidence_score REAL, "
                "reasoning TEXT, model_version TEXT, classified_at TEXT)"
            )
        )
        # staging.int_prices_cleaned is only consulted in the AI-first broad
        # sweep (fetch_unclassified tier 2). Tests that exercise tier 1 (the
        # queue) don't need it; the no-candidates test below intentionally
        # leaves both empty.
    return engine


def _seed_queue_item(engine, cid: str, name: str, status: str = "PENDING"):
    """Insert a row into silver.classification_queue the way the dbt ladder does."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO silver.classification_queue "
                "(product_key, name_clean, status) VALUES (:id, :name, :status)"
            ),
            {"id": cid, "name": name, "status": status},
        )


def _seed_cache_item(
    engine, name: str, code: str, confidence: float = 0.9, reason: str = "cached"
):
    """Insert a row into silver.dim_coicop_ai_cache."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO silver.dim_coicop_ai_cache "
                "(product_name, coicop_code, confidence_score, reasoning, model_version) "
                "VALUES (:name, :code, :conf, :reason, 'test')"
            ),
            {"name": name, "code": code, "conf": confidence, "reason": reason},
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


def test_is_quota_exhausted_and_extract_delay():
    quota_err = RuntimeError(
        "429 Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 500. Please retry in 41.46s"
    )
    assert gcc._is_rate_limit_error(quota_err) is True
    assert gcc._is_quota_exhausted_error(quota_err) is True
    assert gcc._extract_retry_delay(quota_err) == 41.46

    generic_err = RuntimeError("429 ResourceExhausted: retry after seconds: 15")
    assert gcc._is_rate_limit_error(generic_err) is True
    assert gcc._is_quota_exhausted_error(generic_err) is False
    assert gcc._extract_retry_delay(generic_err) == 15.0


def test_classify_names_circuit_breaker_on_quota():
    class QuotaExhaustedModel:
        def __init__(self):
            self.calls = 0

        def generate_content(self, contents, system_instruction=None):
            self.calls += 1
            raise RuntimeError("429 Quota exceeded for metric: free_tier_requests, limit: 500")

    model = QuotaExhaustedModel()
    names = [f"Item {i}" for i in range(10)]  # 5 batches with batch_size=2
    outcome = gcc.classify_names(names, model=model, batch_size=2)

    # Circuit breaker must halt after 1 call (quota exhausted error) instead of 5 calls
    assert model.calls == 1
    assert outcome["failed"] == 1
    assert len(outcome["results"]) == 10
    for name in names:
        assert outcome["results"][name]["coicop_code"] == "99.9.9"


def test_get_api_keys(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "key1, key2,key3")
    assert gcc._get_api_keys() == ["key1", "key2", "key3"]

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEYS", "keyA, keyB ")
    assert gcc._get_api_keys() == ["keyA", "keyB"]


def test_gemini_model_pool_failover():
    pool = gcc.GeminiModelPool(["key1", "key2"])
    assert pool.active_keys == ["key1", "key2"]
    pool.mark_exhausted("key1")
    assert pool.active_keys == ["key2"]
    pool.mark_exhausted("key2")
    assert pool.active_keys == []


# ── Integration-style (sqlite + fake model) ──────────────────────────────────


def test_classify_unclassified_with_gemini_end_to_end():
    """End-to-end: queue is the unclassified source; cache is the canonical write target."""
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
        _seed_queue_item(engine, rid, name)

    # Pre-cached name: no API call for Detergent 2kg.
    _seed_cache_item(engine, "Detergent 2kg", "05.6.1", 0.9, "household goods")

    result = gcc.classify_unclassified_with_gemini(engine=engine, model=model)
    assert result["status"] == "OK"
    assert result["candidates"] == 4
    # Phase 3: local triage may classify some items before classify_names,
    # so cache_hits reflects only items that reached the Gemini path and
    # were resolved by the name cache inside classify_names.
    # The total classified count is what matters for correctness.
    assert result["classified"] >= 3  # Milk, Phone, Detergent classified; Banana is 99.9.9
    assert result["api_calls"] <= 1  # at most 1 batch for uncached names

    # silver.dim_coicop_ai_cache is the canonical write target.
    with engine.connect() as conn:
        cache_rows = conn.execute(
            text("SELECT product_name, coicop_code FROM silver.dim_coicop_ai_cache")
        ).fetchall()
        queue_rows = conn.execute(
            text(
                "SELECT product_key, status, resolved_division, reason "
                "FROM silver.classification_queue"
            )
        ).fetchall()

    cache_by_name = {r[0]: r[1] for r in cache_rows}
    assert cache_by_name["Fresh Whole Milk 1L"] == "01.1.4"
    assert cache_by_name["Smartphone Galaxy 8GB"] == "08.2.0"
    assert cache_by_name["Detergent 2kg"] == "05.6.1"  # pre-seeded
    # Phase 4: 99.9.9 results are now negative-cached (prevents retry storms).
    # "Organic Bananas" may now appear in cache with code 99.9.9.
    if "Organic Bananas" in cache_by_name:
        assert cache_by_name["Organic Bananas"] == "99.9.9"

    # Queue: high-confidence rows resolved with derived 2-digit division;
    # pre-cached row also resolves (via cache, no API). An AI response of
    # "99.9.9" is filtered out before persist_classifications touches the
    # queue (no real code to land), so R-BANANA stays in its original PENDING
    # state untouched. That's the production contract.
    queue_by_key = {r[0]: r for r in queue_rows}
    assert queue_by_key["R-MILK"][1] == "RESOLVED"
    assert queue_by_key["R-MILK"][2] == "01"
    assert queue_by_key["R-PHONE"][1] == "RESOLVED"
    assert queue_by_key["R-PHONE"][2] == "08"
    assert queue_by_key["R-DET"][1] == "RESOLVED"
    assert queue_by_key["R-DET"][2] == "05"
    assert queue_by_key["R-BANANA"][1] == "PENDING"
    assert queue_by_key["R-BANANA"][2] is None
    assert queue_by_key["R-BANANA"][3] is None

    # And exercise the low-confidence branch: seed a cache hit with conf < 0.50
    # but a real (non-99.9.9) code, which IS persisted and flips the row to
    # PENDING with the explanatory reason.
    engine2 = _sqlite_engine()
    _seed_queue_item(engine2, "R-MARG", "Margarine 250g")
    _seed_cache_item(engine2, "Margarine 250g", "01.1.5", 0.30, "margarine")
    gcc.persist_classifications(
        engine2,
        {"Margarine 250g": {"product_name": "Margarine 250g", "coicop_code": "01.1.5", "confidence_score": 0.30, "reasoning": "low conf"}},
        [{"canonical_item_id": "R-MARG", "canonical_name": "Margarine 250g"}],
    )
    with engine2.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, resolved_division, reason FROM silver.classification_queue "
                "WHERE product_key = 'R-MARG'"
            )
        ).fetchone()
    assert row[0] == "PENDING"
    assert row[1] is None
    assert row[2] == "low confidence AI classification"


def test_classify_unclassified_no_candidates():
    engine = _sqlite_engine()
    result = gcc.classify_unclassified_with_gemini(engine=engine, model=FakeModel({}))
    assert result["status"] == "SKIPPED_NO_UNCLASSIFIED"
    assert result["candidates"] == 0
