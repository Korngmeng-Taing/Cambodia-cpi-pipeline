"""
tests/test_canonical.py
───────────────────────
Unit tests for the Canonical Bronze Contract (pipeline.canonical, Schema v1.0).
"""

import pytest

from pipeline.canonical import normalize_record, normalize_records, validate_record


def test_normalize_record_full_schema():
    rec = normalize_record(
        {
            "source_slug": "delishop",
            "store": "Delishop Cambodia",
            "item_id": "18492",
            "name": "Angkor Beer Can 330ml",
            "price": 0.85,
            "original_price": 0.95,
            "barcode": "8850188800123",
            "brand": "Angkor",
            "category_native": "Beers & Ciders",
            "currency": "USD",
            "scrape_date": "2026-08-17",
        }
    )
    assert rec["source_slug"] == "delishop"
    assert rec["store"] == "Delishop Cambodia"
    assert rec["item_id"] == "18492"
    assert rec["name"] == "Angkor Beer Can 330ml"
    assert rec["price"] == 0.85
    assert rec["original_price"] == 0.95
    assert rec["on_promo"] is True
    assert rec["discount_pct"] == pytest.approx(10.53, rel=1e-2)
    assert rec["promo"] == {"type": "discount", "value": 0.1}
    assert rec["barcode"] == "8850188800123"
    assert rec["cpi_eligible"] is True
    assert rec["is_fallback"] is False
    assert rec["unit"] == "UNIT"


def test_normalize_record_tolerates_raw_scrape_keys():
    raw = {
        "product_id": "SKU-001",
        "name": "PREMIUM JASMINE RICE 5KG",
        "price": 22000,
        "original_price": 25000,
        "currency": "KHR",
        "brand": "Angkor Harvest",
        "barcode": "8850123456789",
        "category": "Rice & Grains",
        "scraped_at": "2026-08-17T03:00:00Z",
    }
    rec = normalize_record(raw, source_slug="sample_market", scrape_date="2026-08-17")
    assert rec["item_id"] == "SKU-001"
    assert rec["source_slug"] == "sample_market"
    assert rec["currency"] == "KHR"
    assert rec["category_native"] == "Rice & Grains"
    assert rec["on_promo"] is True
    assert rec["discount_pct"] == 12.0


def test_normalize_record_requires_price():
    with pytest.raises(ValueError):
        normalize_record({"name": "No Price Item", "source_slug": "x"})


def test_normalize_record_price_bounds():
    with pytest.raises(ValueError):
        normalize_record({"name": "Absurd", "price": -5.0, "source_slug": "x"})
    with pytest.raises(ValueError):
        normalize_record({"name": "Absurd", "price": 1e12, "source_slug": "x"})


def test_normalize_records_list():
    recs = normalize_records(
        [
            {"name": "A", "price": 1.0, "source_slug": "x"},
            {"name": "B", "price": 2.0, "source_slug": "x"},
        ],
        scrape_date="2026-08-17",
    )
    assert len(recs) == 2
    assert all(r["scrape_date"] == "2026-08-17" for r in recs)


def test_validate_record_missing_required():
    rec = normalize_record({"name": "A", "price": 1.0, "source_slug": "x"})
    issues = validate_record(rec)
    assert issues == []

    broken = dict(rec)
    broken["name"] = None
    assert any("name" in i for i in validate_record(broken))

    bad_discount = dict(rec)
    bad_discount["discount_pct"] = 150.0
    assert any("discount_pct" in i for i in validate_record(bad_discount))


def test_normalize_record_rejects_missing_slug():
    with pytest.raises(ValueError, match="missing required source_slug"):
        normalize_record({"name": "Item", "price": 1.0})


def test_normalize_record_rejects_zero_price():
    with pytest.raises(ValueError, match="missing valid positive price"):
        normalize_record({"name": "Free Item", "price": 0.0, "source_slug": "store_a"})


def test_normalize_record_boolean_string_parsing():
    rec = normalize_record(
        {"name": "Item", "price": 5.0, "source_slug": "store_a", "is_fallback": "false", "on_promo": "False"}
    )
    assert rec["is_fallback"] is False
    assert rec["on_promo"] is False


def test_normalize_record_currency_normalization():
    rec = normalize_record(
        {"name": "Item", "price": 5000.0, "source_slug": "store_a", "currency": "khr"}
    )
    assert rec["currency"] == "KHR"


def test_validate_record_promo_requires_payload():
    rec = normalize_record({"name": "A", "price": 1.0, "source_slug": "x"})
    rec["on_promo"] = True
    rec["promo"] = None
    assert any("promo" in i for i in validate_record(rec))


def test_currency_inference_defaults():
    # Transport portals default to USD
    rec_bus = normalize_record({"name": "Bus ticket", "price": 12.0, "source_slug": "redbus"})
    assert rec_bus["currency"] == "USD"
    rec_bmb = normalize_record({"name": "Bus ticket", "price": 8.5, "source_slug": "bookmebus"})
    assert rec_bmb["currency"] == "USD"

    # GrabMart and AEON stores default to KHR
    rec_grab = normalize_record({"name": "Milk 1L", "price": 8500.0, "source_slug": "grab_lucky"})
    assert rec_grab["currency"] == "KHR"
    rec_ucare = normalize_record({"name": "Panadol", "price": 6000.0, "source_slug": "grab_ucare"})
    assert rec_ucare["currency"] == "KHR"
    rec_aeon3 = normalize_record({"name": "Shirt", "price": 35000.0, "source_slug": "aeon3"})
    assert rec_aeon3["currency"] == "KHR"
