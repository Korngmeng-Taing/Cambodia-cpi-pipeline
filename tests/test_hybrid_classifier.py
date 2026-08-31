from pipeline.hybrid_embeddings_classifier import HybridCOICOPClassifier


def test_pure_store_domain_purity():
    classifier = HybridCOICOPClassifier()

    # Gas station must be instantly locked to 07 (Fuel)
    res_gas = classifier.classify_product("Super 95 Gasoline", store_slug="new_gasoline")
    assert res_gas["coicop_division"] == "07"
    assert res_gas["classification_method"] == "store_purity"

    # Telecom must be locked to 08
    res_tel = classifier.classify_product("Monthly Data Plan 10GB", store_slug="cellcard")
    assert res_tel["coicop_division"] == "08"
    assert res_tel["classification_method"] == "store_purity"


def test_community_pharma_split():
    classifier = HybridCOICOPClassifier()

    # Panadol / Medicine should classify strictly into 06 (Health / Pharmaceuticals)
    res_med = classifier.classify_product("Panadol Extra 500mg Tablets", store_slug="communitypharma")
    assert res_med["coicop_division"] == "06"
    assert res_med["coicop_code"] == "06.1.1"

    # Cetaphil / Skincare should classify strictly into 12 (Personal Care)
    res_skin = classifier.classify_product("Cetaphil Gentle Skin Cleanser 500ml", store_slug="communitypharma")
    assert res_skin["coicop_division"] == "12"
    assert res_skin["coicop_code"] == "12.1.3"



def test_reference_vectors_loaded():
    classifier = HybridCOICOPClassifier()
    assert len(classifier._ref_embeddings) == 12
    divisions = [ref["division"] for ref in classifier._ref_embeddings]
    for expected_div in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"):
        assert expected_div in divisions

    # Verify 4-digit reference taxonomy is populated
    assert len(classifier._ref_embeddings_4digit) >= 35
    codes = [r["code"] for r in classifier._ref_embeddings_4digit]
    assert "01.1.1" in codes  # Bread & Cereals
    assert "01.1.2" in codes  # Meat
    assert "01.1.3" in codes  # Fish & Seafood
    assert "02.1.3" in codes  # Beer
    assert "06.1.1" in codes  # Pharmaceuticals
    assert "07.2.2" in codes  # Vehicle Fuels
    assert "12.1.1" in codes  # Hair Care


def test_khmer_text_classification():
    """Verify that pure and mixed Khmer retail items classify correctly."""
    classifier = HybridCOICOPClassifier()

    # Pure Khmer Fish -> Division 01 / Class 01.1.3
    res_fish = classifier.classify_product("ត្រីសាម៉ុងស្រស់ 500g")
    assert res_fish["coicop_division"] == "01"
    assert res_fish["coicop_code"] == "01.1.3"

    # Pure Khmer Beef -> Division 01 / Class 01.1.2
    res_beef = classifier.classify_product("សាច់គោស្រស់ 1kg")
    assert res_beef["coicop_division"] == "01"
    assert res_beef["coicop_code"] == "01.1.2"

    # Pure Khmer Beer -> Division 02 / Class 02.1.3
    res_beer = classifier.classify_product("ស្រាបៀរអង្គរ កំប៉ុង 330ml")
    assert res_beer["coicop_division"] == "02"
    assert res_beer["coicop_code"] == "02.1.3"

    # Pure Khmer Fuel -> Division 07 / Class 07.2.2
    res_gas = classifier.classify_product("សាំងធម្មតា 1L")
    assert res_gas["coicop_division"] == "07"
    assert res_gas["coicop_code"] == "07.2.2"

    # Pure Khmer Shampoo -> Division 12 / Class 12.1.1
    res_shampoo = classifier.classify_product("សាប៊ូកក់សក់ Clear 400ml")
    assert res_shampoo["coicop_division"] == "12"
    assert res_shampoo["coicop_code"] == "12.1.1"


def test_4digit_coicop_resolution():
    """Verify granular 4-digit / 5-digit COICOP class resolution across categories."""
    classifier = HybridCOICOPClassifier()

    # Bread and cereals
    res_rice = classifier.classify_product_4digit("Jasmine Rice 5kg")
    assert res_rice["coicop_division"] == "01"
    assert res_rice["coicop_code"] == "01.1.1"
    assert "Bread and cereals" in res_rice["coicop_class_name"]

    # Fish and seafood
    res_salmon = classifier.classify_product_4digit("Fresh Salmon Fillet 300g")
    assert res_salmon["coicop_division"] == "01"
    assert res_salmon["coicop_code"] == "01.1.3"
    assert "Fish" in res_salmon["coicop_class_name"]

    # Pharmaceuticals
    res_med = classifier.classify_product_4digit("Paracetamol 500mg Tablets")
    assert res_med["coicop_division"] == "06"
    assert res_med["coicop_code"] == "06.1.1"

    # Automotive fuel
    res_fuel = classifier.classify_product_4digit("Super 95 Gasoline 1L")
    assert res_fuel["coicop_division"] == "07"
    assert res_fuel["coicop_code"] == "07.2.2"

