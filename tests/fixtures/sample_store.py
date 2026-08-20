"""
scrapers/sample_store.py
────────────────────────
Sample store scraper implementation for local development and testing.
"""

from __future__ import annotations

from typing import Any

import pendulum

from scrapers.base import BaseScraper


class SampleStoreScraper(BaseScraper):
    """
    Mock scraper returning realistic sample catalog records.
    """

    def __init__(self, store_slug: str = "sample_market"):
        super().__init__(store_slug=store_slug, source_type="api_mock")

    def fetch_records(self, scrape_date: pendulum.Date | None = None) -> list[dict[str, Any]]:
        now_ts = pendulum.now("UTC").to_iso8601_string()
        return [
            {
                "product_id": "SKU-001",
                "name": "PREMIUM JASMINE RICE 5KG",
                "price": 22000,
                "original_price": 25000,
                "currency": "KHR",
                "brand": "Angkor Harvest",
                "barcode": "8850123456789",
                "category": "Rice & Grains",
                "on_promo": True,
                "scraped_at": now_ts,
            },
            {
                "product_id": "SKU-002",
                "name": "FRESH WHOLE MILK 1L",
                "price": 9500,
                "original_price": 9500,
                "currency": "KHR",
                "brand": "Kirisu Farm",
                "barcode": "8850987654321",
                "category": "Dairy",
                "on_promo": False,
                "scraped_at": now_ts,
            },
            {
                "product_id": "SKU-003",
                "name": "NATURAL DISHWASHING LIQUID 750ML",
                "price": 6800,
                "original_price": 7500,
                "currency": "KHR",
                "brand": "Earth Clean",
                "barcode": "8850555666777",
                "category": "Household",
                "on_promo": True,
                "scraped_at": now_ts,
            },
        ]
