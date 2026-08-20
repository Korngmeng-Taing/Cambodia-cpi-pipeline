"""
scrapers/base.py
────────────────
Abstract Base Scraper class enforcing standard interface for Bronze ingestion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pendulum


class BaseScraper(ABC):
    """
    Abstract interface for CPI store scrapers.
    All scrapers return a list of raw dictionary records adhering to the Bronze contract.
    """

    def __init__(self, store_slug: str, source_type: str = "web"):
        self.store_slug = store_slug
        self.source_type = source_type

    @abstractmethod
    def fetch_records(self, scrape_date: pendulum.Date | None = None) -> list[dict[str, Any]]:
        """
        Extracts raw product and price records for the target store.

        Returns:
            List of dictionaries containing raw item keys (name, price, currency, etc.).
        """
        raise NotImplementedError

    def scrape(self, scrape_date: pendulum.Date | None = None) -> dict[str, Any]:
        """
        Executes scrape and packages the payload with metadata for Bronze staging upsert.
        """
        if scrape_date is None:
            scrape_date = pendulum.today("Asia/Phnom_Penh").date()

        records = self.fetch_records(scrape_date=scrape_date)
        return {
            "store_slug": self.store_slug,
            "source_type": self.source_type,
            "scrape_date": str(scrape_date),
            "record_count": len(records),
            "records": records,
        }
