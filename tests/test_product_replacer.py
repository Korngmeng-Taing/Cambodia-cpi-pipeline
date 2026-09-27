"""
tests/test_product_replacer.py
Unit tests for the ProductReplacer module.
"""

from datetime import date
from unittest.mock import MagicMock

from pipeline.product_replacer import ProductReplacer


def test_product_replacer_direct_equivalent():
    replacer = ProductReplacer(name_similarity_threshold=0.80)
    missing = [
        {
            "item_id": "old_rice_01",
            "store_slug": "aeon",
            "coicop_code": "01.1.1",
            "name_clean": "Jasmine Rice Angkor 5kg",
            "package_size_normalized": 5.0,
        }
    ]
    new_items = [
        {
            "item_id": "new_rice_01",
            "store_slug": "aeon",
            "coicop_code": "01.1.1",
            "name_clean": "Angkor Jasmine Rice 5kg",
            "package_size_normalized": 5.0,
        }
    ]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value.mogrify.return_value = b"SQL;"
    results = replacer.find_and_record_replacements(
        calc_date=date(2026, 9, 27),
        missing_items=missing,
        new_items=new_items,
        conn=mock_conn,
    )

    assert len(results) == 1
    assert results[0]["old_item_id"] == "old_rice_01"
    assert results[0]["new_item_id"] == "new_rice_01"
    assert results[0]["replacement_type"] == "DIRECT_EQUIVALENT"
    assert results[0]["quality_adjustment_factor"] == 1.0


def test_product_replacer_quantity_adjusted():
    replacer = ProductReplacer(name_similarity_threshold=0.80)
    missing = [
        {
            "item_id": "old_coke",
            "store_slug": "lucky",
            "coicop_code": "01.2.2",
            "name_clean": "Coca Cola Can 330ml",
            "package_size_normalized": 0.33,
        }
    ]
    # Replaced by shrinkflated 300ml version
    new_items = [
        {
            "item_id": "new_coke",
            "store_slug": "lucky",
            "coicop_code": "01.2.2",
            "name_clean": "Coca Cola Can 300ml",
            "package_size_normalized": 0.30,
        }
    ]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value.mogrify.return_value = b"SQL;"
    results = replacer.find_and_record_replacements(
        calc_date=date(2026, 9, 27),
        missing_items=missing,
        new_items=new_items,
        conn=mock_conn,
    )

    assert len(results) == 1
    assert results[0]["replacement_type"] == "QUANTITY_ADJUSTED"
    assert round(results[0]["quality_adjustment_factor"], 2) == round(0.30 / 0.33, 2)


def test_product_replacer_no_match():
    replacer = ProductReplacer(name_similarity_threshold=0.80)
    missing = [
        {
            "item_id": "old_beef",
            "store_slug": "aeon",
            "coicop_code": "01.1.2",
            "name_clean": "Australian Beef Sirloin 1kg",
        }
    ]
    new_items = [
        {
            "item_id": "new_chicken",
            "store_slug": "aeon",
            "coicop_code": "01.1.2",
            "name_clean": "Fresh Whole Chicken 1kg",
        }
    ]

    mock_conn = MagicMock()
    results = replacer.find_and_record_replacements(
        calc_date=date(2026, 9, 27),
        missing_items=missing,
        new_items=new_items,
        conn=mock_conn,
    )

    assert len(results) == 0
