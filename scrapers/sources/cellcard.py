from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

import pendulum
import requests

try:
    from curl_cffi import requests as cffi_requests

    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from pipeline.canonical import normalize_record
from pipeline.config import DEFAULT_USD_KHR_RATE
from scrapers.base import BaseScraper
from scrapers.sources._common import (
    THROTTLE_DELAY,
    _cffi_get,
    _cffi_post,
    _strip_html,
    _to_float,
    build_canonical_record,
    log,
)


# 7. Cellcard Mobile — Next.js & Tariff Matrix (Telecom)
# ═══════════════════════════════════════════════════════════════════════════
CELLCARD_MOBILE_URL = "https://www.cellcard.com.kh/en/mobile"

CELLCARD_MOBILE_PLANS = [
    {
        "id": "cell_biglove_150",
        "name": "Cellcard Big Love $1.50 (20GB / 7 Days)",
        "price": 1.50,
        "type": "Mobile Prepaid > Weekly Data",
        "data": "20GB",
    },
    {
        "id": "cell_biglove_300",
        "name": "Cellcard Big Love $3.00 (50GB / 14 Days)",
        "price": 3.00,
        "type": "Mobile Prepaid > Bi-Weekly Data",
        "data": "50GB",
    },
    {
        "id": "cell_biglove_600",
        "name": "Cellcard Big Love $6.00 (120GB / 30 Days)",
        "price": 6.00,
        "type": "Mobile Prepaid > Monthly Data",
        "data": "120GB",
    },
    {
        "id": "cell_serey_100",
        "name": "Cellcard Serey Unlimited Calls + 10GB",
        "price": 1.00,
        "type": "Mobile Prepaid > Voice & Data",
        "data": "10GB",
    },
    {
        "id": "cell_tourist_5g",
        "name": "Cellcard 5G Tourist SIM 30-Day Pass",
        "price": 10.00,
        "type": "Mobile Prepaid > Tourist SIM",
        "data": "80GB",
    },
]

CELLCARD_WIFI_URL = "https://www.cellcard.com.kh/en/home-internet/"

CELLCARD_WIFI_PLANS = [
    {
        "id": "cell_wifi_20m",
        "name": "Cellcard Home Wi-Fi Basic 20 Mbps",
        "price": 12.00,
        "type": "Broadband Internet > Home Wi-Fi",
        "speed": "20 Mbps",
    },
    {
        "id": "cell_wifi_50m",
        "name": "Cellcard Fiber Internet Standard 50 Mbps",
        "price": 18.00,
        "type": "Broadband Internet > Fiber Internet",
        "speed": "50 Mbps",
    },
    {
        "id": "cell_wifi_100m",
        "name": "Cellcard Fiber Ultra High-Speed 100 Mbps",
        "price": 25.00,
        "type": "Broadband Internet > Fiber Internet",
        "speed": "100 Mbps",
    },
]


class CellcardScraper(BaseScraper):
    """Combined Cellcard Scraper covering both Mobile and Home Internet / Fiber plans."""

    def __init__(self, store_slug: str = "cellcard"):
        super().__init__(store_slug=store_slug, source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        # 1. Scrape Mobile Plans
        try:
            resp = _cffi_get(CELLCARD_MOBILE_URL, timeout=15)
            if resp.status_code == 200 and HAS_BS4:
                soup = BeautifulSoup(resp.text, "html.parser")
                script = soup.find("script", id="__NEXT_DATA__")
                if script and script.string:
                    next_data = json.loads(script.string)
                    props = next_data.get("props", {}).get("pageProps", {})
                    for key in ("plans", "mobilePlans", "data"):
                        plans = props.get(key)
                        if isinstance(plans, list) and plans:
                            for idx, plan in enumerate(plans):
                                name = plan.get("name") or plan.get("title") or ""
                                price = _to_float(
                                    plan.get("price") or plan.get("monthly_price")
                                )
                                if price and name:
                                    records.append(
                                        build_canonical_record(
                                            source_slug=self.store_slug,
                                            source_type="telecom",
                                            store_name="Cellcard Cambodia Mobile",
                                            item_id=str(
                                                plan.get("id", f"cell_mob_{idx}")
                                            ),
                                            name=name,
                                            price=price,
                                            currency="USD",
                                            category_native=plan.get("type")
                                            or "Mobile Prepaid",
                                            package_size=plan.get("data"),
                                            url=CELLCARD_MOBILE_URL,
                                            scrape_date=ds,
                                        )
                                    )
        except Exception as exc:
            log.warning("Cellcard Mobile live scrape error: %s", exc)

        if not records:
            for plan in CELLCARD_MOBILE_PLANS:
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type="telecom",
                        store_name="Cellcard Cambodia Mobile",
                        item_id=plan["id"],
                        name=plan["name"],
                        price=plan["price"],
                        currency="USD",
                        category_native=plan["type"],
                        package_size=plan["data"],
                        url=CELLCARD_MOBILE_URL,
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )

        # 2. Add Home Internet / WiFi plans
        for plan in CELLCARD_WIFI_PLANS:
            records.append(
                build_canonical_record(
                    source_slug=self.store_slug,
                    source_type="telecom",
                    store_name="Cellcard Home Internet",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["speed"],
                    url=CELLCARD_WIFI_URL,
                    scrape_date=ds,
                    is_fallback=True,
                )
            )

        return records


# Aliases for backwards compatibility
CellcardMobileScraper = CellcardScraper


class CellcardWifiScraper(BaseScraper):
    """Retained for backwards compatibility if referenced directly."""

    def __init__(self):
        super().__init__(store_slug="cellcard_wifi", source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        for plan in CELLCARD_WIFI_PLANS:
            records.append(
                build_canonical_record(
                    source_slug="cellcard_wifi",
                    source_type="telecom",
                    store_name="Cellcard Home Internet",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["speed"],
                    url=CELLCARD_WIFI_URL,
                    scrape_date=ds,
                    is_fallback=True,
                )
            )
        return records
