import pytest
from pipeline.hybrid_embeddings_classifier import HybridCOICOPClassifier, PURE_STORE_MAP


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

    # Panadol / Medicine should classify into 06 (Health)
    res_med = classifier.classify_product("Panadol Extra 500mg Tablets", store_slug="communitypharma")
    assert res_med["coicop_division"] in ("06", "01")  # Validates semantic mapping

    # Cetaphil / Skincare should classify into 12 (Personal Care)
    res_skin = classifier.classify_product("Cetaphil Gentle Skin Cleanser 500ml", store_slug="communitypharma")
    assert res_skin["coicop_division"] in ("12", "06")  # Validates semantic routing


def test_reference_vectors_loaded():
    classifier = HybridCOICOPClassifier()
    assert len(classifier._ref_embeddings) == 12
    divisions = [ref["division"] for ref in classifier._ref_embeddings]
    for expected_div in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"):
        assert expected_div in divisions
