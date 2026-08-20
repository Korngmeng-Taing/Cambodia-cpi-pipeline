"""
tests/test_scrapers.py
──────────────────────
Unit tests for scrapers interface and sample scraper contract.
"""

from __future__ import annotations

from typing import Any

import pendulum

from scrapers.base import BaseScraper


class SampleStoreScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="sample_market", source_type="api_mock")

    def fetch_records(self, scrape_date: pendulum.Date | None = None) -> list[dict[str, Any]]:
        return [
            {"name": "Jasmine Rice 5kg", "price": 25000, "currency": "KHR"},
            {"name": "Cooking Oil 1L", "price": 8500, "currency": "KHR"},
            {"name": "Angkor Beer 330ml", "price": 2500, "currency": "KHR"},
        ]


def test_sample_store_scraper_inherits_base():
    scraper = SampleStoreScraper()
    assert isinstance(scraper, BaseScraper)
    assert scraper.store_slug == "sample_market"
    assert scraper.source_type == "api_mock"


def test_sample_store_scraper_returns_valid_payload():
    scraper = SampleStoreScraper()
    today = pendulum.date(2026, 8, 17)
    payload = scraper.scrape(scrape_date=today)

    assert payload["store_slug"] == "sample_market"
    assert payload["source_type"] == "api_mock"
    assert payload["scrape_date"] == "2026-08-17"
    assert payload["record_count"] == 3
    assert len(payload["records"]) == 3

    for item in payload["records"]:
        assert "name" in item
        assert "price" in item
        assert "currency" in item
        assert item["price"] > 0
