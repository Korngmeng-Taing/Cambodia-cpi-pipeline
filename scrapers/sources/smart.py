from __future__ import annotations

from typing import Any

import pendulum

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    build_canonical_record,
)


# 9. Smart Mobile — Multi-URL & Tariff Matrix (Telecom)
# ═══════════════════════════════════════════════════════════════════════════
SMART_MOBILE_URLS = ["https://www.smart.com.kh/plans"]

SMART_MOBILE_PLANS = [
    {
        "id": "smart_laor_150",
        "name": "Smart Laor! $1.50 (15GB / 7 Days)",
        "price": 1.50,
        "type": "Mobile Prepaid > Weekly Data",
        "data": "15GB",
    },
    {
        "id": "smart_laor_300",
        "name": "Smart Laor! $3.00 (35GB / 14 Days)",
        "price": 3.00,
        "type": "Mobile Prepaid > Bi-Weekly Data",
        "data": "35GB",
    },
    {
        "id": "smart_laor_600",
        "name": "Smart Laor! $6.00 (80GB / 30 Days)",
        "price": 6.00,
        "type": "Mobile Prepaid > Monthly Data",
        "data": "80GB",
    },
    {
        "id": "smart_flexi_250",
        "name": "Smart Flexi250 Data & Voice Bundle",
        "price": 2.50,
        "type": "Mobile Prepaid > Flexi Combo",
        "data": "25GB",
    },
    {
        "id": "smart_tourist_sim",
        "name": "Smart Traveller SIM 30-Day Unlimited",
        "price": 12.00,
        "type": "Mobile Prepaid > Tourist SIM",
        "data": "100GB",
    },
]

SMART_WIFI_PLANS = [
    {
        "id": "smart_athome_40m",
        "name": "Smart @Home Wi-Fi Router 40 Mbps",
        "price": 15.00,
        "type": "Broadband Internet > Wireless Home Internet",
        "speed": "40 Mbps",
    },
    {
        "id": "smart_fiber_60m",
        "name": "Smart Fiber+ Standard 60 Mbps",
        "price": 20.00,
        "type": "Broadband Internet > Fiber Internet",
        "speed": "60 Mbps",
    },
    {
        "id": "smart_fiber_120m",
        "name": "Smart Fiber+ Ultra 120 Mbps",
        "price": 30.00,
        "type": "Broadband Internet > Fiber Internet",
        "speed": "120 Mbps",
    },
]


class SmartScraper(BaseScraper):
    """Combined Smart Axiata Scraper covering both Mobile and Home Internet / WiFi plans."""

    def __init__(self, store_slug: str = "smart"):
        super().__init__(store_slug=store_slug, source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        # 1. Mobile Plans
        for plan in SMART_MOBILE_PLANS:
            records.append(
                build_canonical_record(
                    source_slug=self.store_slug,
                    source_type="telecom",
                    store_name="Smart Cambodia Mobile",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["data"],
                    url="https://www.smart.com.kh/plans",
                    scrape_date=ds,
                    is_fallback=True,
                )
            )

        # 2. Home Internet / WiFi Plans
        for plan in SMART_WIFI_PLANS:
            records.append(
                build_canonical_record(
                    source_slug=self.store_slug,
                    source_type="telecom",
                    store_name="Smart Home Internet",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["speed"],
                    url="https://www.smart.com.kh/home-internet",
                    scrape_date=ds,
                    is_fallback=True,
                )
            )

        return records


# Aliases for backwards compatibility
SmartMobileScraper = SmartScraper


class SmartWifiScraper(BaseScraper):
    """Retained for backwards compatibility if referenced directly."""

    def __init__(self):
        super().__init__(store_slug="smart_wifi", source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        for plan in SMART_WIFI_PLANS:
            records.append(
                build_canonical_record(
                    source_slug="smart_wifi",
                    source_type="telecom",
                    store_name="Smart Home Internet",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["speed"],
                    url="https://www.smart.com.kh/home-internet",
                    scrape_date=ds,
                    is_fallback=True,
                )
            )
        return records
