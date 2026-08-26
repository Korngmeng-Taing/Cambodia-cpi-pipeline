import pytest
from pipeline.vector_item_matcher import extract_specs, is_spec_compatible, VectorItemMatcher


def test_extract_specs():
    # Tech specs
    spec1 = extract_specs("Apple iPhone 15 Pro Max 256GB Natural Titanium")
    assert spec1["storage"] == "256gb"
    assert spec1["pack_qty"] == 1

    # Pack quantities
    spec2 = extract_specs("Coca-Cola Original Taste 330ml Can Pack of 6")
    assert spec2["pack_qty"] == 6
    assert spec2["size_val"] == 330.0
    assert spec2["size_unit"] == "ml"

    spec3 = extract_specs("Angkor Beer 330ml x24 Cans")
    assert spec3["pack_qty"] == 24
    assert spec3["size_val"] == 330.0


def test_is_spec_compatible_guards():
    # 1. Storage conflicts must be rejected (SPLIT_NEW)
    assert not is_spec_compatible(
        "Samsung Galaxy S24 128GB Black",
        "Samsung Galaxy S24 256GB Black"
    )
    assert is_spec_compatible(
        "Samsung Galaxy S24 256GB Black",
        "Samsung Galaxy S24 256GB Gray"
    )

    # 2. Pack size conflicts must be rejected (SPLIT_NEW)
    assert not is_spec_compatible(
        "Coca-Cola 330ml Single Can",
        "Coca-Cola 330ml Pack of 6"
    )
    assert is_spec_compatible(
        "Coca-Cola 330ml Pack of 6",
        "Coca Cola 330ml x6 Cans"
    )

    # 3. Volume/mass conflicts > 10% must be rejected
    assert not is_spec_compatible(
        "Fresh Milk 330ml",
        "Fresh Milk 1000ml"
    )
    assert is_spec_compatible(
        "Cooking Oil 1L",
        "Cooking Oil 1L"
    )


def test_vector_matcher_empty_catalog():
    matcher = VectorItemMatcher()
    res = matcher.match_candidate("Fresh Salmon 500g", [])
    assert res["decision"] == "SPLIT_NEW"
    assert res["matched_item_id"] is None
