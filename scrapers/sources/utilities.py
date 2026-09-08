from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pendulum

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    build_canonical_record,
    log,
)

# ═══════════════════════════════════════════════════════════════════════════
# Official Utilities Tariffs: EDC (Electricity) & PPWSA (Water Supply)
# ═══════════════════════════════════════════════════════════════════════════
EDC_URL = "https://eac.gov.kh/document/tariffdecidelist"
PPWSA_URL = "https://ppwsa.com.kh/kh/index.php?page=customer-service"

# Fallback baseline tariff structures if seed file is inaccessible
EDC_DEFAULT_TARIFFS = [
    {
        "item_id": "edc_elec_380",
        "name": "EDC Residential Electricity Tier 1 (1 - 10 kWh)",
        "rate_khr": 380.0,
        "unit": "kWh",
        "category": "Electricity > Residential Lifeline",
    },
    {
        "item_id": "edc_elec_480",
        "name": "EDC Residential Electricity Tier 2 (11 - 50 kWh)",
        "rate_khr": 480.0,
        "unit": "kWh",
        "category": "Electricity > Residential Low Tier",
    },
    {
        "item_id": "edc_elec_610",
        "name": "EDC Residential Electricity Tier 3 (51 - 200 kWh)",
        "rate_khr": 610.0,
        "unit": "kWh",
        "category": "Electricity > Residential Standard Benchmark",
    },
    {
        "item_id": "edc_elec_730",
        "name": "EDC Residential Electricity Tier 4 (> 200 kWh)",
        "rate_khr": 730.0,
        "unit": "kWh",
        "category": "Electricity > Residential High Consumption",
    },
]

PPWSA_DEFAULT_TARIFFS = [
    {
        "item_id": "ppwsa_water_400",
        "name": "PPWSA Domestic Piped Water Tier 1 (1 - 7 m³)",
        "rate_khr": 400.0,
        "unit": "m3",
        "category": "Water Supply > Domestic Lifeline",
    },
    {
        "item_id": "ppwsa_water_720",
        "name": "PPWSA Domestic Piped Water Tier 2 (8 - 15 m³)",
        "rate_khr": 720.0,
        "unit": "m3",
        "category": "Water Supply > Domestic Low Tier",
    },
    {
        "item_id": "ppwsa_water_960",
        "name": "PPWSA Domestic Piped Water Tier 3 (16 - 30 m³)",
        "rate_khr": 960.0,
        "unit": "m3",
        "category": "Water Supply > Domestic Standard Benchmark",
    },
    {
        "item_id": "ppwsa_water_1250",
        "name": "PPWSA Domestic Piped Water Tier 4 (31 - 50 m³)",
        "rate_khr": 1250.0,
        "unit": "m3",
        "category": "Water Supply > Domestic High Tier",
    },
    {
        "item_id": "ppwsa_water_1900",
        "name": "PPWSA Commercial / Business Water Tier 1 (> 50 m³)",
        "rate_khr": 1900.0,
        "unit": "m3",
        "category": "Water Supply > Commercial / High Volume",
    },
    {
        "item_id": "ppwsa_water_2200",
        "name": "PPWSA Commercial / Business Water Tier 2 (> 100 m³)",
        "rate_khr": 2200.0,
        "unit": "m3",
        "category": "Water Supply > Commercial / High Volume",
    },
]


def _read_utility_tariffs_seed(source: str) -> list[dict[str, Any]]:
    """Reads tariffs directly from dbt/seeds/utility_tariffs.csv if present."""
    seed_path = (
        Path(__file__).resolve().parent.parent.parent
        / "dbt"
        / "seeds"
        / "utility_tariffs.csv"
    )
    results = []
    if seed_path.exists():
        try:
            with open(seed_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("source_name", "").strip().lower() == source.lower():
                        rate = float(row.get("rate_khr", 0))
                        unit = row.get("unit", "")
                        is_rep = str(row.get("is_representative", "")).strip().upper() == "TRUE"
                        results.append({
                            "rate_khr": rate,
                            "unit": unit,
                            "is_representative": is_rep,
                            "effective_from": row.get("effective_from", "2020-01-01"),
                        })
        except Exception as exc:
            log.warning("Could not read utility_tariffs.csv for %s: %s", source, exc)
    return results


class EdcElectricityScraper(BaseScraper):
    """Scraper for Electricité du Cambodge (EDC) regulated electricity tariffs (COICOP 04.5.1)."""

    def __init__(self, store_slug: str = "edc"):
        super().__init__(store_slug=store_slug, source_type="utility")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        seed_data = _read_utility_tariffs_seed("edc")
        if seed_data:
            for item in seed_data:
                rate = item["rate_khr"]
                rep_tag = " (Primary CPI Benchmark)" if item["is_representative"] else ""
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type="utility",
                        store_name="Electricité du Cambodge (EDC)",
                        item_id=f"edc_elec_rate_{int(rate)}",
                        name=f"EDC Regulated Residential Electricity Tariff {int(rate)} KHR/kWh{rep_tag}",
                        price=rate,
                        currency="KHR",
                        category_native="Electricity > Regulated Tariff",
                        package_size=f"1 {item['unit']}",
                        unit=item["unit"],
                        url=EDC_URL,
                        scrape_date=ds,
                        is_fallback=False,
                    )
                )
        else:
            for item in EDC_DEFAULT_TARIFFS:
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type="utility",
                        store_name="Electricité du Cambodge (EDC)",
                        item_id=item["item_id"],
                        name=item["name"],
                        price=item["rate_khr"],
                        currency="KHR",
                        category_native=item["category"],
                        package_size=f"1 {item['unit']}",
                        unit=item["unit"],
                        url=EDC_URL,
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )

        return records


class PpwsaWaterScraper(BaseScraper):
    """Scraper for Phnom Penh Water Supply Authority (PPWSA) regulated municipal water tariffs (COICOP 04.4.1)."""

    def __init__(self, store_slug: str = "ppwsa"):
        super().__init__(store_slug=store_slug, source_type="utility")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        seed_data = _read_utility_tariffs_seed("ppwsa")
        if seed_data:
            for item in seed_data:
                rate = item["rate_khr"]
                rep_tag = " (Primary CPI Benchmark)" if item["is_representative"] else ""
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type="utility",
                        store_name="Phnom Penh Water Supply Authority (PPWSA)",
                        item_id=f"ppwsa_water_rate_{int(rate)}",
                        name=f"PPWSA Municipal Water Supply Tariff {int(rate)} KHR/m³{rep_tag}",
                        price=rate,
                        currency="KHR",
                        category_native="Water Supply > Regulated Tariff",
                        package_size=f"1 {item['unit']}",
                        unit=item["unit"],
                        url=PPWSA_URL,
                        scrape_date=ds,
                        is_fallback=False,
                    )
                )
        else:
            for item in PPWSA_DEFAULT_TARIFFS:
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type="utility",
                        store_name="Phnom Penh Water Supply Authority (PPWSA)",
                        item_id=item["item_id"],
                        name=item["name"],
                        price=item["rate_khr"],
                        currency="KHR",
                        category_native=item["category"],
                        package_size=f"1 {item['unit']}",
                        unit=item["unit"],
                        url=PPWSA_URL,
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )

        return records
