"""
tests/test_gemini_item_reviewer.py
Unit tests for pipeline/gemini_item_reviewer.py covering:
  T1a - APPROVE_MATCH flow
  T1b - SPLIT_NEW flow
  T1c - Rule guard spec conflict detection
  T1d - Batch-scoped barcode lookup (memory safety)
  T1e - Exponential backoff retry
  T1f - dry_run mode
  T4  - size compatibility edge cases (ml<->L, g<->kg)
"""
import json
import uuid
from unittest.mock import MagicMock, patch


from pipeline.gemini_item_reviewer import GeminiItemReviewer, evaluate_rule_guard
from pipeline.text_clean import is_size_compatible


def _make_reviewer():
    reviewer = GeminiItemReviewer.__new__(GeminiItemReviewer)
    reviewer.db_conn_str = "postgresql://x:y@localhost/db"
    reviewer.model_name = "gemini-flash-test"
    reviewer.model = MagicMock()
    return reviewer


def _row(review_id=1, raw_price_id=101, raw_desc="iPhone 13 128GB",
         match_name="iPhone 13 256GB", conf=0.91, store="aeon", barcode=None):
    return {
        "review_id": review_id, "raw_price_id": raw_price_id,
        "item_description_raw": raw_desc, "best_match_item_id": uuid.uuid4(),
        "best_match_name": match_name, "confidence": conf, "store_id": store,
        "price": 4500000, "currency": "KHR", "brand": None,
        "barcode": barcode, "size_norm": None,
    }


def _stats():
    return {"total_pending": 0, "rule_approved": 0, "rule_split": 0,
            "ai_approved": 0, "ai_split": 0, "skipped": 0}


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = []
    cur.mogrify.return_value = b"MOCK_SQL"
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


# ── T1c: Rule Guard ───────────────────────────────────────────────────────────

class TestRuleGuard:
    def test_storage_gb_mismatch_forces_split(self):
        result = evaluate_rule_guard("iPhone 13 128GB", "iPhone 13 256GB")
        assert result is not None
        decision, _, _reason = result
        assert decision == "SPLIT_NEW"

    def test_wattage_mismatch_forces_split(self):
        result = evaluate_rule_guard("Electric Kettle 1000W", "Electric Kettle 2000W")
        assert result is not None
        assert result[0] == "SPLIT_NEW"

    def test_screen_size_mismatch_forces_split(self):
        # 43 inch vs 55 inch TV should split
        result = evaluate_rule_guard("UA43DU8100KXXT SAMSUNG", "UA55DU8100KXXT SAMSUNG")
        assert result is not None
        assert result[0] == "SPLIT_NEW"
        assert "screen" in result[2] or "model_code" in result[2]

    def test_btu_mismatch_forces_split(self):
        # 18000 BTU vs 24000 BTU AC should split
        result = evaluate_rule_guard("AR18DYHZBWKNST SAMSUNG", "AR24DYHZBWKNST SAMSUNG")
        assert result is not None
        assert result[0] == "SPLIT_NEW"
        assert "btu" in result[2] or "model_code" in result[2]

    def test_model_code_mismatch_forces_split(self):
        # ST90B vs ST40B sound tower should split
        result = evaluate_rule_guard("MX-ST90B/XT SAMSUNG", "MX-ST40B/XT SAMSUNG")
        assert result is not None
        assert result[0] == "SPLIT_NEW"

    def test_no_spec_conflict_defers_to_ai(self):
        result = evaluate_rule_guard("Coca Cola Original 330ml", "Coca Cola 330ml")
        if result is not None:
            assert result[0] != "SPLIT_NEW"


# ── T1a: APPROVE_MATCH flow ───────────────────────────────────────────────────

class TestApproveMatch:
    def test_ai_approved_increments_ai_approved_stat(self):
        reviewer = _make_reviewer()
        conn, _cur = _mock_conn()
        row = _row(review_id=10, raw_price_id=200, match_name="Coca Cola 330ml")
        pair_decisions = {1: {"decision": "APPROVE_MATCH", "confidence": 0.95,
                              "reason": "AI ok", "method": "gemini_ai", "rows": [row]}}
        stats = _stats()
        reviewer._apply_decisions(conn, pair_decisions, stats)
        assert stats["ai_approved"] == 1

    def test_rule_approved_increments_rule_approved_stat(self):
        reviewer = _make_reviewer()
        conn, _cur = _mock_conn()
        row = _row(review_id=11, raw_price_id=201)
        pair_decisions = {1: {"decision": "APPROVE_MATCH", "confidence": 1.0,
                              "reason": "rule guard", "method": "rule_guard", "rows": [row]}}
        stats = _stats()
        reviewer._apply_decisions(conn, pair_decisions, stats)
        assert stats["rule_approved"] == 1
        assert stats["ai_approved"] == 0


# ── T1b: SPLIT_NEW flow ───────────────────────────────────────────────────────

class TestSplitNew:
    def test_split_increments_ai_split_stat(self):
        reviewer = _make_reviewer()
        conn, _cur = _mock_conn()
        row = _row(review_id=20, raw_price_id=300, raw_desc="Samsung S24 256GB")
        pair_decisions = {1: {"decision": "SPLIT_NEW", "confidence": 0.85,
                              "reason": "spec conflict", "method": "gemini_ai", "rows": [row]}}
        stats = _stats()
        reviewer._apply_decisions(conn, pair_decisions, stats)
        assert stats["ai_split"] == 1

    def test_existing_barcode_routes_to_barcode_approved(self):
        reviewer = _make_reviewer()
        conn, cur = _mock_conn()
        existing_id = uuid.uuid4()
        cur.fetchall.return_value = [("8850006070451", existing_id)]
        row = _row(review_id=21, raw_price_id=301, barcode="8850006070451")
        pair_decisions = {1: {"decision": "SPLIT_NEW", "confidence": 0.85,
                              "reason": "Variant", "method": "gemini_ai", "rows": [row]}}
        stats = _stats()
        reviewer._apply_decisions(conn, pair_decisions, stats)
        assert stats["rule_approved"] == 1
        assert stats["ai_split"] == 0


# ── T1d: Batch-scoped barcode lookup ─────────────────────────────────────────

class TestBatchBarcode:
    def test_barcode_query_uses_any(self):
        reviewer = _make_reviewer()
        conn, cur = _mock_conn()
        row = _row(review_id=30, raw_price_id=400, barcode="123456789")
        pair_decisions = {1: {"decision": "SPLIT_NEW", "confidence": 0.85,
                              "reason": "split", "method": "rule_guard", "rows": [row]}}
        stats = _stats()
        reviewer._apply_decisions(conn, pair_decisions, stats)
        execute_calls = [str(c) for c in cur.execute.mock_calls]
        for s in execute_calls:
            if "canonical_items" in s and "barcode" in s:
                assert "ANY" in s, "Barcode lookup must use ANY(%s) to avoid full table scan"


# ── T1e: Exponential backoff retry ───────────────────────────────────────────

class TestGeminiRetry:
    def test_retries_then_succeeds(self):
        reviewer = _make_reviewer()
        good = MagicMock()
        good.text = json.dumps([
            {"pair_id": 1, "decision": "APPROVE_MATCH", "confidence": 0.95, "reason": "ok"}
        ])
        reviewer.model.generate_content.side_effect = [
            Exception("503"), Exception("503"), good
        ]
        pairs = [{"pair_id": 1, "raw_name": "A", "candidate_name": "A", "store": "s"}]
        with patch("pipeline.gemini_item_reviewer.time.sleep"):
            results = reviewer.resolve_with_gemini(pairs)
        assert results[1]["decision"] == "APPROVE_MATCH"
        assert reviewer.model.generate_content.call_count == 3

    def test_all_fail_returns_empty(self):
        reviewer = _make_reviewer()
        reviewer.model.generate_content.side_effect = Exception("Persistent")
        pairs = [{"pair_id": 1, "raw_name": "A", "candidate_name": "B", "store": "x"}]
        with patch("pipeline.gemini_item_reviewer.time.sleep"):
            results = reviewer.resolve_with_gemini(pairs)
        assert results == {}


# ── T1f: dry_run mode ────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_call_apply_decisions(self):
        reviewer = _make_reviewer()
        pending = [_row(review_id=i, raw_price_id=100 + i) for i in range(3)]
        with patch.object(reviewer, "_get_connection") as mock_cf, \
             patch.object(reviewer, "fetch_pending_reviews", return_value=pending), \
             patch.object(reviewer, "_apply_decisions") as mock_apply, \
             patch.object(reviewer, "resolve_with_gemini", return_value={}):
            mock_cf.return_value = MagicMock()
            stats = reviewer.process_all_pending(limit=10, dry_run=True)
        mock_apply.assert_not_called()
        assert stats["total_pending"] == 3


# ── T4: Size compatibility edge cases ────────────────────────────────────────

class TestSizeCompatibility:
    def test_330ml_equals_0_33L(self):
        assert is_size_compatible("330ml", "0.33L")

    def test_1000ml_equals_1L(self):
        assert is_size_compatible("1000ml", "1L")

    def test_500g_equals_0_5kg(self):
        assert is_size_compatible("500g", "0.5kg")

    def test_500g_vs_2kg_incompatible(self):
        assert not is_size_compatible("500g", "2kg")

    def test_volume_vs_weight_incompatible(self):
        assert not is_size_compatible("500ml", "500g")

    def test_none_always_compatible(self):
        assert is_size_compatible(None, "330ml")
        assert is_size_compatible("330ml", None)
        assert is_size_compatible(None, None)

    def test_within_tolerance(self):
        assert is_size_compatible("500g", "540g", tolerance=0.10)

    def test_exceeds_tolerance(self):
        assert not is_size_compatible("500g", "600g", tolerance=0.10)

