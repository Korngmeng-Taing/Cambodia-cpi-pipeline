"""
scrapers/sources/nis_cpi.py
───────────────────────────
Scraper & Ingestion Worker for National Institute of Statistics (NIS) Official CPI Releases.

Ingests official monthly headline & core CPI numbers into the Cambodia CPI pipeline
for ground-truth validation, nowcasting calibration, and chain-linking.
"""

from __future__ import annotations

import logging
from typing import Any

import pendulum

from pipeline.nis_cpi_importer import NISBenchmarkImporter
from scrapers.base import BaseScraper, OnEmpty
from scrapers.sources._common import build_canonical_record

log = logging.getLogger(__name__)


class NISCPIScraper(BaseScraper):
    """Scrapes/imports official NIS Cambodia monthly CPI press releases."""

    on_empty = OnEmpty.FALLBACK_STATIC

    def __init__(self):
        super().__init__(store_slug="nis_official_cpi", source_type="official_benchmark")
        self.importer = NISBenchmarkImporter()

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        """Queries NIS portal or returns latest ground-truth records."""
        records = self.importer.fetch_from_portal()
        if not records:
            log.info("NIS portal returned 0 dynamic releases; reading local synchronized seed.")
            import csv
            import os

            ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
            if os.path.exists(self.importer.seed_file_path):
                with open(self.importer.seed_file_path, encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        records.append(
                            build_canonical_record(
                                source_slug="nis_official_cpi",
                                source_type="official_benchmark",
                                store_name="National Institute of Statistics (NIS)",
                                item_id=f"nis_cpi_{r.get('cpi_month')}",
                                name=f"NIS Official CPI {r.get('cpi_month')}",
                                price=float(r.get("headline_cpi", 100.0)),
                                currency="KHR",
                                category_native="Official Macro CPI",
                                scrape_date=ds,
                                attrs=r,
                                is_fallback=True,
                            )
                        )
        return records
