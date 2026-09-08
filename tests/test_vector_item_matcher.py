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
    assert not is_spec_compatible(
        "Cooking Oil 1L",
        "Cooking Oil 1.15L"  # 15% difference -> rejected
    )
    assert is_spec_compatible(
        "Cooking Oil 1L",
        "Cooking Oil 1.05L"  # 5% difference (within 10% tolerance) -> accepted
    )
    # 4. Screen size conflicts must be rejected (SPLIT_NEW)
    assert not is_spec_compatible(
        "UA43DU8100KXXT SAMSUNG 43 inch 4K TV",
        "UA55DU8100KXXT SAMSUNG 55 inch 4K TV"
    )

    # 5. Appliance / Electronic model code conflicts must be rejected (SPLIT_NEW)
    assert not is_spec_compatible(
        "MX-ST90B/XT SAMSUNG Sound Tower",
        "MX-ST40B/XT SAMSUNG Sound Tower"
    )
    assert not is_spec_compatible(
        "AR18DYHZBWKNST SAMSUNG Inverter Air Conditioner",
        "AR24DYHZBWKNST SAMSUNG Inverter Air Conditioner"
    )



def test_vector_matcher_empty_catalog():
    matcher = VectorItemMatcher()
    res = matcher.match_candidate("Fresh Salmon 500g", [])
    assert res["decision"] == "SPLIT_NEW"
    assert res["matched_item_id"] is None


def test_embed_texts_and_batch_matching():
    matcher = VectorItemMatcher()
    texts = ["Angkor Beer 330ml Can", "Coca-Cola 330ml Can", "Fresh Salmon 500g"]
    vecs = matcher.embed_texts(texts, batch_size=2)
    assert vecs.shape == (3, 768)

    catalog = [
        {"item_id": "item-1", "canonical_name": "Angkor Beer 330ml Can"},
        {"item_id": "item-2", "canonical_name": "Coca-Cola 330ml Can"},
    ]
    res = matcher.match_candidate("Angkor Beer 330ml Can", catalog)
    assert res["decision"] == "APPROVE_MATCH"
    assert res["matched_item_id"] == "item-1"


def test_match_candidate_db_pgvector_hnsw():
    from unittest.mock import MagicMock
    matcher = VectorItemMatcher()

    # Mock database connection and cursor simulating pgvector HNSW result
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Mock query returning: item_id, canonical_name, brand, size_norm, coicop_div, coicop_code, cos_sim
    mock_cur.fetchall.return_value = [
        ("uuid-1234", "Angkor Premium Beer 330ml", "Angkor", "330ml", "02", "02.1.3", 0.94)
    ]

    res = matcher.match_candidate_db("Angkor Beer 330ml", mock_conn, sim_auto_threshold=0.80)
    assert res is not None
    assert res["decision"] == "APPROVE_MATCH"
    assert res["matched_item_id"] == "uuid-1234"
    assert res["method"] == "vector_embedding"
    assert res["coicop_division"] == "02"
    assert res["confidence"] == 0.94

