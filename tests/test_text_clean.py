"""
test_text_clean.py — C2 regression: package sizes survive text cleaning.

Before the C2 fix, _RE_PRICE matched bare "<digits><letters>" (e.g. "330ml",
"500g") because the suffix was optional, so it stripped them thinking they
were prices. The cleaned name lost its size signal and `silver.canonical_items`
deduplicated "Coca Cola 330ml" against "Coca Cola 500g" under one UUID.

The new _RE_PRICE requires an explicit currency prefix ($ / ៛) or suffix
(USD / KHR / RIEL / ៛ / $) — never a bare number followed by a unit.

This test mirrors the contract enforced by
`dbt/tests/test_size_preserved_in_name.sql` on the dbt side.
"""

from pipeline.text_clean import (
    clean_name_for_matching,
    full_normalize,
    segment_khmer_words,
)


class TestPriceStrip:
    """True prices (currency-anchored) must still be stripped."""

    def test_dollar_price_stripped(self):
        assert clean_name_for_matching("Coca-Cola $1.99") == "COCA-COLA"

    def test_khr_price_stripped(self):
        assert clean_name_for_matching("Coca-Cola 4000KHR") == "COCA-COLA"

    def test_usd_price_stripped(self):
        assert clean_name_for_matching("Coca-Cola USD 1.99") == "COCA-COLA"

    def test_khmer_numeral_price_stripped(self):
        # ៛៥០០០ (KHR 5000 in Khmer numerals) must still be stripped.
        assert clean_name_for_matching("Coca-Cola ៛៥០០០") == "COCA-COLA"

    def test_price_with_promo(self):
        assert (
            clean_name_for_matching("Coca-Cola 330ml SALE $1.99")
            == "COCA-COLA 330ML"
        )


class TestSizePreserved:
    """Package sizes (no currency anchor) must NOT be stripped."""

    def test_ml_size_preserved(self):
        assert clean_name_for_matching("Angkor Beer 330ml") == "ANGKOR BEER 330ML"

    def test_g_size_preserved(self):
        assert clean_name_for_matching("Sugar 500g") == "SUGAR 500G"

    def test_kg_size_preserved(self):
        assert clean_name_for_matching("Rice 1kg") == "RICE 1KG"

    def test_l_size_preserved(self):
        assert clean_name_for_matching("Cooking Oil 2L") == "COOKING OIL 2L"

    def test_oz_size_preserved(self):
        assert clean_name_for_matching("Coffee 8oz") == "COFFEE 8OZ"

    def test_decimal_size_preserved(self):
        assert clean_name_for_matching("Milk 0.5L") == "MILK 0.5L"

    def test_mixed_size_and_brand(self):
        assert (
            clean_name_for_matching("Coca-Cola Original 330ml x 6")
            == "COCA-COLA ORIGINAL 330ML X 6"
        )


class TestKhmerOrdering:
    """H9 fix: Khmer compounds must translate as a single term, not split."""

    def test_milk_not_water_beef(self):
        # ទឹកដោះគោ = MILK (compound). Must not split into WATER ... BEEF.
        result = clean_name_for_matching("ទឹកដោះគោ 1L")
        assert "WATER" not in result, f"got {result!r}"
        assert "BEEF" not in result, f"got {result!r}"
        assert "MILK" in result, f"got {result!r}"

    def test_diesel_compound(self):
        # ប្រេងម៉ាស៊ូត = DIESEL. Must not split into GASOLINE + DIESEL.
        result = clean_name_for_matching("ប្រេងម៉ាស៊ូត")
        assert result.count("DIESEL") == 1
        assert "GASOLINE" not in result

    def test_pork_compound(self):
        # សាច់ជ្រូក = PORK.
        result = clean_name_for_matching("សាច់ជ្រូក")
        assert "PORK" in result
        # No spurious word order issue.
        assert "CHICKEN" not in result


class TestFullNormalize:
    def test_full_pipeline_preserves_size(self):
        assert (
            full_normalize("Coca-Cola SALE $1.99 330ml")
            == "COCA-COLA 330ML"
        )

    def test_full_pipeline_preserves_size_with_promo(self):
        result = full_normalize("Angkor Beer 330ml PROMO")
        assert "330ML" in result
        assert "PROMO" not in result

    def test_full_pipeline_handles_none(self):
        assert full_normalize(None) == ""

    def test_full_pipeline_handles_empty(self):
        assert full_normalize("") == ""


class TestEdgeCases:
    def test_none_input(self):
        assert clean_name_for_matching(None) == ""

    def test_empty_string(self):
        assert clean_name_for_matching("") == ""

    def test_whitespace_only(self):
        assert clean_name_for_matching("   ") == ""

    def test_html_entity_decode(self):
        assert (
            clean_name_for_matching("Tom &amp; Jerry 250ml")
            == "TOM & JERRY 250ML"
        )

    def test_multiple_promos_stripped(self):
        result = clean_name_for_matching("SALE Hot Deal Coca-Cola 330ml")
        assert "SALE" not in result
        assert "HOT DEAL" not in result.replace("HOT", "").replace("DEAL", "")
        assert "330ML" in result


class TestSegmentKhmerLongestFirst:
    def test_segment_khmer_words_longest_first(self):
        # Direct unit test for the H9 longest-first ordering in the helper.
        assert segment_khmer_words("ទឹកដោះគោ") == "MILK"
        assert segment_khmer_words("ប្រេងម៉ាស៊ូត") == "DIESEL"
        assert segment_khmer_words("សាច់ជ្រូក") == "PORK"
