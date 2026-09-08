"""
tests/test_matching_accuracy.py
───────────────────────────────
Accuracy tests for the product matching ladder:
  - Fuzzy text matching with real-world Cambodian retail product names
  - Spec guard preventing false merges (storage, pack size, volume, diet)
  - Size compatibility across unit conversions (g↔kg, ml↔L)
  - Khmer/English product name matching
  - Edge cases: promo words, prices, HTML entities, abbreviation expansion
  - Full matching ladder priority (barcode > SKU > exact > fuzzy > new)
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from pipeline.item_matcher import ItemMatcher
from pipeline.text_clean import (
    clean_name_for_matching,
    expand_abbreviations,
    full_normalize,
    is_size_compatible,
    segment_khmer_words,
)
from pipeline.vector_item_matcher import (
    extract_specs,
    is_spec_compatible,
    _build_semantic_item_vector,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TEXT NORMALIZATION ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestTextNormalizationAccuracy:
    """Ensure clean_name_for_matching produces correct normalized output."""

    @pytest.mark.parametrize("raw,expected", [
        # Price stripping (currency-anchored only)
        ("Coca Cola 330ml $1.99", "COCA COLA 330ML"),
        ("Rice 5kg 4,000KHR", "RICE 5KG"),
        ("Fish Sauce USD 2.50", "FISH SAUCE"),
        ("Sugar 1kg ៛3000", "SUGAR 1KG"),
        # Package size preserved (C2 regression)
        ("Milk 330ml", "MILK 330ML"),
        ("Rice 500g", "RICE 500G"),
        ("Oil 1.5L", "OIL 1.5L"),
        ("Juice 1000ml", "JUICE 1000ML"),
        # Promo word stripping
        ("Coca Cola SALE 330ml", "COCA COLA 330ML"),
        ("Rice PROMO 5kg", "RICE 5KG"),
        ("Milk DISCOUNT 1L", "MILK 1L"),
        ("Bread CLEARANCE 500g", "BREAD 500G"),
        ("Oil HOT DEAL 1.5L", "OIL 1.5L"),
        # HTML entities
        ("Coca-Cola &amp; Company", "COCA-COLA & COMPANY"),
        ("Rice #39;s Best", "RICE #39;S BEST"),
        # Leading/trailing noise
        ("  Coca Cola  ", "COCA COLA"),
        ("---Rice 5kg---", "RICE 5KG"),
        # Empty/None
        ("", ""),
        (None, ""),
        ("   ", ""),
        # Price NOT stripped when no currency anchor
        ("Coca Cola 330ml", "COCA COLA 330ML"),
        ("Milk 1000g Bundle", "MILK 1000G"),
    ])
    def test_clean_name_normalization(self, raw, expected):
        assert clean_name_for_matching(raw) == expected

    def test_khmer_compound_longest_first(self):
        """H9 fix: multi-char Khmer compounds must not be split."""
        result = segment_khmer_words("ទឹកដោះគោ")
        assert result == "MILK"
        # Must NOT produce "WATER MILK BEEF" (compound split regression)

    @pytest.mark.parametrize("raw,expected", [
        ("សាំង", "GASOLINE"),
        ("អង្ករ", "RICE"),
        ("ត្រី", "FISH"),
        ("សាច់គោ", "BEEF"),
        ("សាច់ជ្រូក", "PORK"),
        ("សាច់មាន់", "CHICKEN"),
        ("ទឹកដោះគោ", "MILK"),
        ("ស្បែកជើង", "SHOES"),
        ("ទូរស័ព្ទ", "PHONE"),
    ])
    def test_khmer_translation(self, raw, expected):
        result = segment_khmer_words(raw)
        assert expected in result

    def test_khmer_numeral_conversion(self):
        """Khmer digits ០១២... should map to 012..."""
        result = full_normalize("អង្ករ ៥ គីឡូ")
        assert "5" in result
        assert "៤" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SPEC EXTRACTION ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpecExtraction:
    """Ensure extract_specs correctly parses storage, pack_qty, size_val/unit."""

    @pytest.mark.parametrize("text,expected", [
        ("iPhone 13 128GB", {"storage": "128gb", "pack_qty": 1, "size_val": None, "size_unit": None}),
        ("Samsung S24 256GB", {"storage": "256gb", "pack_qty": 1, "size_val": None, "size_unit": None}),
        ("MacBook Pro 1TB", {"storage": "1tb", "pack_qty": 1, "size_val": None, "size_unit": None}),
        ("Coca Cola 330ml x6", {"storage": None, "pack_qty": 6, "size_val": 330.0, "size_unit": "ml"}),
        ("Coca Cola 24x330ml", {"storage": None, "pack_qty": 24, "size_val": 330.0, "size_unit": "ml"}),
        ("Water Case of 24 500ml", {"storage": None, "pack_qty": 24, "size_val": 500.0, "size_unit": "ml"}),
        ("Beer Pack of 12", {"storage": None, "pack_qty": 12, "size_val": None, "size_unit": None}),
        ("Milk 1L", {"storage": None, "pack_qty": 1, "size_val": 1.0, "size_unit": "l"}),
        ("Rice 5kg", {"storage": None, "pack_qty": 1, "size_val": 5.0, "size_unit": "kg"}),
        ("Juice 500ml", {"storage": None, "pack_qty": 1, "size_val": 500.0, "size_unit": "ml"}),
        ("Snacks x24", {"storage": None, "pack_qty": 24, "size_val": None, "size_unit": None}),
        ("", {"storage": None, "pack_qty": 1, "size_val": None, "size_unit": None}),
        (None, {"storage": None, "pack_qty": 1, "size_val": None, "size_unit": None}),
    ])
    def test_extract_specs(self, text, expected):
        result = extract_specs(text)
        for k, v in expected.items():
            assert result.get(k) == v


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SPEC GUARD ACCURACY (Prevent False Merges)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpecGuardAccuracy:
    """Deterministic guard must reject merges when specs conflict."""

    @pytest.mark.parametrize("cand,base,expected", [
        # Storage conflicts → must reject
        ("iPhone 13 128GB", "iPhone 13 256GB", False),
        ("Samsung S24 128GB", "Samsung S24 512GB", False),
        ("Laptop 256GB SSD", "Laptop 1TB SSD", False),
        # Same storage → compatible
        ("iPhone 13 128GB", "iPhone 13 128GB", True),
        ("Samsung S24 256GB", "Samsung S24 256GB", True),
        # Pack quantity conflicts → must reject
        ("Coca Cola 330ml x6", "Coca Cola 330ml", False),
        ("Beer 500ml x12", "Beer 500ml x6", False),
        ("Water 1.5L Pack of 4", "Water 1.5L", False),
        # Same pack qty → compatible
        ("Coca Cola 330ml", "Coca Cola 330ml", True),
        ("Beer 500ml x6", "Beer 500ml x6", True),
        # Volume/mass conflicts (>10% diff) → must reject
        ("Milk 500ml", "Milk 1000ml", False),
        ("Rice 500g", "Rice 2kg", False),
        ("Oil 500ml", "Oil 2L", False),
        # Compatible sizes (within 10% tolerance)
        ("Milk 330ml", "Milk 330ml", True),
        ("Rice 1kg", "Rice 1kg", True),
        # Diet/Original flavor conflict → must reject
        ("Coca Cola Zero 330ml", "Coca Cola 330ml", False),
        ("Pepsi Light 500ml", "Pepsi 500ml", False),
        ("Diet Coke 330ml", "Coke 330ml", False),
        # Same diet variant → compatible
        ("Coca Cola Zero 330ml", "Coca Cola Zero 330ml", True),
        ("Pepsi Light 500ml", "Pepsi Light 500ml", True),
        # No specs → compatible (permissive)
        ("Coca Cola", "Coca Cola", True),
        ("Rice", "Rice", True),
        # Cross-dimensional (volume vs mass) → no conflict
        ("Milk 500ml", "Milk 500g", False),  # Different units, not compatible
    ])
    def test_spec_guard(self, cand, base, expected):
        assert is_spec_compatible(cand, base) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SIZE COMPATIBILITY ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestSizeCompatibility:
    """Cross-normalize g↔kg and ml↔L; check tolerance."""

    @pytest.mark.parametrize("s1,s2,expected", [
        # Same unit
        ("500g", "500g", True),
        ("1L", "1L", True),
        ("330ml", "330ml", True),
        ("5kg", "5kg", True),
        # Cross-normalize g ↔ kg
        ("100g", "0.1kg", True),
        ("500g", "0.5kg", True),
        ("1000g", "1kg", True),
        ("250g", "0.25kg", True),
        # Cross-normalize ml ↔ L
        ("500ml", "0.5L", True),
        ("1000ml", "1L", True),
        ("330ml", "0.33L", True),
        ("1500ml", "1.5L", True),
        # Within tolerance (10%)
        ("500g", "540g", True),
        ("500g", "460g", True),
        ("1L", "1.05L", True),
        ("330ml", "350ml", True),
        # Exceeds tolerance
        ("500g", "600g", False),
        ("500g", "400g", False),
        ("1L", "1.2L", False),
        ("330ml", "500ml", False),
        # Cross-dimensional (incompatible)
        ("500ml", "500g", False),
        ("1L", "1kg", False),
        # None is permissive
        (None, "500g", True),
        ("500g", None, True),
        (None, None, True),
    ])
    def test_size_compatibility(self, s1, s2, expected):
        assert is_size_compatible(s1, s2) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FUZZY MATCHING ACCURACY (Real-World Product Pairs)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFuzzyMatchingAccuracy:
    """Test fuzzy matching against real-world Cambodian retail product pairs."""

    def _make_matcher_with_catalog(self, catalog_names):
        """Create an ItemMatcher with pre-loaded catalog for testing."""
        matcher = ItemMatcher.__new__(ItemMatcher)
        matcher.auto_accept_threshold = 0.95
        matcher.review_threshold = 0.85
        matcher.barcode_cache = {}
        matcher.exact_name_cache = {}
        matcher.sku_cache = {}
        matcher.items_cache = []
        matcher._vector_matcher = None

        for name in catalog_names:
            item_id = uuid.uuid4()
            clean = clean_name_for_matching(name)
            matcher.exact_name_cache[clean.upper()] = item_id
            matcher.items_cache.append((item_id, clean.upper(), None))

        return matcher

    @pytest.mark.parametrize("candidate,catalog_names,should_match", [
        # Near-identical names → should match
        (
            "Coca Cola 330ml",
            ["Coca Cola 330ML", "Pepsi 330ml", "Fanta 330ml"],
            True,
        ),
        # Brand + size variant → should match
        (
            "Milk 1L Whole",
            ["Milk 1L Whole", "Milk 1L Skim", "Juice 1L"],
            True,
        ),
        # Completely different → should not match
        (
            "iPhone 13 128GB",
            ["Coca Cola 330ml", "Rice 5kg", "Milk 1L"],
            False,
        ),
        # Slight spelling difference → should match
        (
            "Coca-Cola 330ml",
            ["COCA COLA 330ML", "Pepsi 330ml"],
            True,
        ),
        # Different sizes → should not match
        (
            "Milk 500ml",
            ["Milk 1L", "Milk 330ml"],
            False,
        ),
    ])
    def test_fuzzy_text_matching(self, candidate, catalog_names, should_match):
        matcher = self._make_matcher_with_catalog(catalog_names)
        clean = clean_name_for_matching(candidate)
        result = matcher.match_by_fuzzy_text(clean, None)

        if should_match:
            assert result is not None, f"Expected match for '{candidate}' but got None"
            _, score, _ = result
            assert score >= 0.85, f"Expected score >= 0.85 for '{candidate}', got {score}"
        else:
            # If it matches, score should be below review threshold
            if result is not None:
                _, score, _ = result
                assert score < 0.85, f"Expected no match for '{candidate}', but got score {score}"

    def test_exact_name_match(self):
        """Exact name match should return score 1.0."""
        matcher = self._make_matcher_with_catalog(["COCA COLA 330ML"])
        result = matcher.match_by_fuzzy_text("COCA COLA 330ML", None)
        assert result is not None
        _, score, name = result
        assert score == 1.0
        assert name == "COCA COLA 330ML"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MATCHING LADDER PRIORITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestMatchingLadderPriority:
    """Barcode > SKU > Exact Name > Fuzzy > New Item."""

    def setup_method(self):
        self.matcher = ItemMatcher.__new__(ItemMatcher)
        self.matcher.auto_accept_threshold = 0.95
        self.matcher.review_threshold = 0.85
        self.matcher.barcode_cache = {}
        self.matcher.exact_name_cache = {}
        self.matcher.sku_cache = {}
        self.matcher.items_cache = []
        self.matcher._vector_matcher = None
        self.matcher._has_embedding_column = False

    def test_barcode_beats_all(self):
        """Barcode match should win over fuzzy and exact name."""
        item_id = uuid.uuid4()
        self.matcher.barcode_cache["12345"] = item_id
        self.matcher.exact_name_cache["COCA COLA 330ML"] = uuid.uuid4()

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn.cursor.return_value.__enter__.return_value = cursor

        stats = self.matcher.match_record(
            raw_price_id=1,
            item_description_raw="Coca Cola 330ml",
            barcode="12345",
            store_id="aeon",
            conn=conn,
        )
        assert stats["matched_exact"] == 1
        assert stats["matched_fuzzy"] == 0
        assert stats["new_items_created"] == 0

    def test_sku_beats_fuzzy(self):
        """SKU match should win over fuzzy."""
        item_id = uuid.uuid4()
        self.matcher.sku_cache[("aeon", "SKU-001")] = item_id

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn.cursor.return_value.__enter__.return_value = cursor

        stats = self.matcher.match_record(
            raw_price_id=2,
            item_description_raw="Some Product",
            sku="SKU-001",
            store_id="aeon",
            conn=conn,
        )
        assert stats["matched_exact"] == 1

    def test_exact_name_beats_fuzzy(self):
        """Exact cleaned name should beat fuzzy."""
        item_id = uuid.uuid4()
        self.matcher.exact_name_cache["COCA COLA 330ML"] = item_id

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn.cursor.return_value.__enter__.return_value = cursor

        stats = self.matcher.match_record(
            raw_price_id=3,
            item_description_raw="Coca Cola 330ml",
            store_id="aeon",
            conn=conn,
        )
        assert stats["matched_fuzzy"] == 1

    def test_no_match_creates_new_item(self):
        """When no match found, new canonical item should be created."""
        conn = MagicMock()
        cursor = MagicMock()
        new_id = uuid.uuid4()
        cursor.fetchone.return_value = (new_id,)
        conn.cursor.return_value.__enter__.return_value = cursor

        with patch("pipeline.item_matcher.get_hybrid_classifier") as mock_cls:
            mock_cls.return_value.classify_product.return_value = {
                "coicop_division": "01",
                "coicop_code": "01.1.1",
            }
            stats = self.matcher.match_record(
                raw_price_id=4,
                item_description_raw="Unique New Product XYZ",
                store_id="aeon",
                conn=conn,
            )
        assert stats["new_items_created"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 7. VEHICLE VECTOR MATCHING (Deterministic Fallback)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeterministicVector:
    """Test the deterministic fallback vector builder for semantic similarity."""

    def test_similar_products_have_higher_similarity(self):
        """Coca Cola variants should be more similar to each other than to Rice."""
        vec_coke = _build_semantic_item_vector("Coca Cola 330ml")
        vec_coke_variant = _build_semantic_item_vector("Coca Cola 500ml")
        vec_rice = _build_semantic_item_vector("Jasmine Rice 5kg")

        import numpy as np

        sim_coke = float(np.dot(vec_coke, vec_coke_variant) / (
            np.linalg.norm(vec_coke) * np.linalg.norm(vec_coke_variant)
        ))
        sim_rice = float(np.dot(vec_coke, vec_rice) / (
            np.linalg.norm(vec_coke) * np.linalg.norm(vec_rice)
        ))

        assert sim_coke > sim_rice, f"Coke-Coke sim ({sim_coke}) should exceed Coke-Rice sim ({sim_rice})"

    def test_khmer_english_synonym_boost(self):
        """Khmer product names should have boosted similarity to English equivalents."""
        vec_khmer = _build_semantic_item_vector("ស្រាបៀរអង្គរ")
        vec_english = _build_semantic_item_vector("angkor beer")
        vec_unrelated = _build_semantic_item_vector("coca cola 330ml")

        import numpy as np

        sim_synonym = float(np.dot(vec_khmer, vec_english) / (
            np.linalg.norm(vec_khmer) * np.linalg.norm(vec_english)
        ))
        sim_unrelated = float(np.dot(vec_khmer, vec_unrelated) / (
            np.linalg.norm(vec_khmer) * np.linalg.norm(vec_unrelated)
        ))

        assert sim_synonym > sim_unrelated, f"Khmer-English sim ({sim_synonym}) should exceed Khmer-unrelated ({sim_unrelated})"

    def test_empty_input_returns_zero_vector(self):
        vec = _build_semantic_item_vector("")
        assert vec.shape == (768,)
        assert vec.sum() == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. ABBREVIATION EXPANSION ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestAbbreviationExpansion:
    """Ensure common product abbreviations are expanded correctly."""

    @pytest.mark.parametrize("raw,expected_contains", [
        ("Coca Cola ORG 330ml", "ORGANIC"),
        ("Rice SPK 5kg", "SPICY"),
        ("Milk FF 1L", "FAT FREE"),
        ("Oil LT 1.5L", "LIGHT"),
        ("Bread REG 500g", "REGULAR"),
        ("Snacks FAM 200g", "FAMILY"),
        ("Milk SM 330ml", "SMALL"),
        ("Juice LG 1L", "LARGE"),
        ("Tea PKT 25x", "PACK"),
        ("Coffee BTL 500ml", "BOTTLE"),
        ("Sauce DLX 250ml", "DELUXE"),
        ("Rice PREM 5kg", "PREMIUM"),
        ("Bread ORIG 500g", "ORIGINAL"),
    ])
    def test_expand_abbreviations(self, raw, expected_contains):
        result = expand_abbreviations(raw)
        assert expected_contains in result, f"Expected '{expected_contains}' in '{result}'"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. EDGE CASE ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary conditions and unusual inputs."""

    def test_very_long_product_name(self):
        """Long names should not cause errors."""
        long_name = "A" * 500 + " 330ml"
        result = clean_name_for_matching(long_name)
        assert len(result) <= 510  # Should be truncated or handled

    def test_special_characters(self):
        """Special chars should be cleaned or preserved appropriately."""
        result = clean_name_for_matching("Coca-Cola®™ 330ml")
        assert "COCA-COLA" in result

    def test_unicode_mixed_content(self):
        """Mixed Khmer + English should be handled."""
        result = clean_name_for_matching("Coca Cola 330ml កូកាកូឡា")
        assert "COCA COLA" in result

    def test_whitespace_variations(self):
        """Multiple whitespace, tabs, newlines should collapse."""
        result = clean_name_for_matching("Coca\tCola\n\n330ml")
        assert "COCA COLA 330ML" == result

    def test_price_only_input(self):
        """Input that's only a price should return empty."""
        result = clean_name_for_matching("$1.99")
        assert result == ""

    def test_size_with_decimal(self):
        """Decimal sizes should be extracted correctly."""
        specs = extract_specs("Milk 1.5L")
        assert specs["size_val"] == 1.5
        assert specs["size_unit"] == "l"

    def test_no_size_returns_none(self):
        """Products without sizes should have None."""
        specs = extract_specs("Coca Cola Original")
        assert specs["size_val"] is None
        assert specs["size_unit"] is None
        assert specs["storage"] is None
        assert specs["pack_qty"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 10. BATCH PROCESSING ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatchProcessingAccuracy:
    """Test process_batch with a realistic mix of records."""

    def test_batch_returns_totals_dict(self):
        """process_batch should return a dict with expected keys."""
        matcher = ItemMatcher.__new__(ItemMatcher)
        matcher.auto_accept_threshold = 0.95
        matcher.review_threshold = 0.85
        matcher.barcode_cache = {}
        matcher.exact_name_cache = {}
        matcher.sku_cache = {}
        matcher.items_cache = []
        matcher._vector_matcher = None

        conn = MagicMock()
        cursor = MagicMock()
        cursor.mogrify.side_effect = lambda sql, args: b"MOCK_SQL"
        cursor.fetchall.side_effect = [
            # canonical_items cache (4 columns)
            [],
            # SKU cache query
            [],
            # Raw prices to process — empty means nothing to do
            [],
        ]
        conn.cursor.return_value.__enter__.return_value = cursor

        totals = matcher.process_batch(conn)

        assert "matched_exact" in totals
        assert "matched_fuzzy" in totals
        assert "sent_to_review" in totals
        assert "new_items_created" in totals
        assert totals["matched_exact"] == 0
        assert totals["new_items_created"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
