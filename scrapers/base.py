"""
scrapers/base.py
───────────────
Abstract Base Scraper class enforcing standard interface for Bronze ingestion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

import pendulum

SCRAPER_SCHEMA_VERSION = "2026-08-28-v1"


class OnEmpty(Enum):
    RAISE = "raise"
    FALLBACK_STATIC = "fallback_static"


class BaseScraper(ABC):
    """
    Abstract interface for CPI store scrapers.
    All scrapers return a list of raw dictionary records adhering to the Bronze contract.
    """

    on_empty: OnEmpty = OnEmpty.FALLBACK_STATIC

    def __init__(self, store_slug: str, source_type: str = "web"):
        self.store_slug = store_slug
        self.source_type = source_type

    @abstractmethod
    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        """
        Extracts raw product and price records for the target store.

        Returns:
            List of dictionaries containing raw item keys (name, price, currency, etc.).
        """
        raise NotImplementedError

    async def fetch_records_async(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        """
        Asynchronously extracts raw product and price records.
        Defaults to running synchronous fetch_records in a threadpool executor.
        Subclasses can override for native async I/O with concurrency semaphores.
        """
        import asyncio
        return await asyncio.to_thread(self.fetch_records, scrape_date=scrape_date)

    def scrape(self, scrape_date: pendulum.Date | None = None) -> dict[str, Any]:
        """
        Executes scrape and packages the payload with metadata for Bronze staging upsert.
        """
        if scrape_date is None:
            scrape_date = pendulum.today("Asia/Phnom_Penh").date()

        ds = self._scrape_date_str(scrape_date)
        records = self.fetch_records(scrape_date=scrape_date)

        if not records and self.on_empty is OnEmpty.RAISE:
            raise RuntimeError(
                f"{self.store_slug}: 0 records scraped on {ds} (on_empty=RAISE)"
            )

        stamped = [self._stamp(r) for r in records]
        return {
            "store_slug": self.store_slug,
            "source_type": self.source_type,
            "scrape_date": ds,
            "schema_version": SCRAPER_SCHEMA_VERSION,
            "record_count": len(stamped),
            "records": stamped,
        }

    async def scrape_async(
        self, scrape_date: pendulum.Date | None = None
    ) -> dict[str, Any]:
        """
        Asynchronously executes scrape and packages payload.
        """
        if scrape_date is None:
            scrape_date = pendulum.today("Asia/Phnom_Penh").date()

        ds = self._scrape_date_str(scrape_date)
        records = await self.fetch_records_async(scrape_date=scrape_date)

        if not records and self.on_empty is OnEmpty.RAISE:
            raise RuntimeError(
                f"{self.store_slug}: 0 records scraped on {ds} (on_empty=RAISE)"
            )

        stamped = [self._stamp(r) for r in records]
        return {
            "store_slug": self.store_slug,
            "source_type": self.source_type,
            "scrape_date": ds,
            "schema_version": SCRAPER_SCHEMA_VERSION,
            "record_count": len(stamped),
            "records": stamped,
        }

    @staticmethod
    def _scrape_date_str(scrape_date: pendulum.Date | None) -> str:
        if scrape_date is None:
            scrape_date = pendulum.today("Asia/Phnom_Penh").date()
        return str(scrape_date)

    def _stamp(self, record: dict[str, Any]) -> dict[str, Any]:
        attrs = dict(record.get("attrs") or {})
        attrs.setdefault("_schema_version", SCRAPER_SCHEMA_VERSION)
        record["attrs"] = attrs
        return record
