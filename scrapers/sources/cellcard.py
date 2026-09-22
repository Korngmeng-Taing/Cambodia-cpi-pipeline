from __future__ import annotations

import json
import re
from typing import Any

import pendulum



try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    _cffi_get,
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
        "name": "Cellcard Serey Unlimited Calls + 10GB (7 Days)",
        "price": 1.00,
        "type": "Mobile Prepaid > Voice & Data",
        "data": "10GB",
    },
    {
        "id": "cell_serey_150",
        "name": "Cellcard Serey Unlimited Calls + 20GB (7 Days)",
        "price": 1.50,
        "type": "Mobile Prepaid > Voice & Data",
        "data": "20GB",
    },
    {
        "id": "cell_play_50c",
        "name": "Cellcard Play 50c Daily Game & Data (2GB / 1 Day)",
        "price": 0.50,
        "type": "Mobile Prepaid > Daily Gaming",
        "data": "2GB",
    },
    {
        "id": "cell_play_250",
        "name": "Cellcard Play $2.50 Gamer Pack (25GB / 7 Days)",
        "price": 2.50,
        "type": "Mobile Prepaid > Weekly Gaming",
        "data": "25GB",
    },
    {
        "id": "cell_tourist_7d",
        "name": "Cellcard 5G Tourist SIM 7-Day Pass (15GB)",
        "price": 5.00,
        "type": "Mobile Prepaid > Tourist SIM",
        "data": "15GB",
    },
    {
        "id": "cell_tourist_5g",
        "name": "Cellcard 5G Tourist SIM 30-Day Pass (80GB)",
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
                seen_names: set[str] = set()
                # Target headings and card containers in the Next.js rendered DOM
                for h4 in soup.find_all("h4"):
                    name = h4.get_text(" ", strip=True).replace("\u200b", "").strip()
                    if not name or len(name) > 80 or name in seen_names:
                        continue
                    # Check if price is in heading itself or parent card
                    m_name_price = re.search(r"\$\s*(\d+(\.\d+)?)", name)
                    parent_text = h4.parent.get_text(" ", strip=True) if h4.parent else ""
                    m_parent_price = re.search(r"\$\s*(\d+(\.\d+)?)", parent_text)

                    price = (
                        _to_float(m_name_price.group(1))
                        if m_name_price
                        else (_to_float(m_parent_price.group(1)) if m_parent_price else None)
                    )
                    if price and price > 0:
                        seen_names.add(name)
                        m_data = re.search(r"(\d+\s*GB)", parent_text, re.I)
                        m_val = re.search(r"(\d+\s*Days?)", parent_text, re.I)
                        pkg_size = m_data.group(1) if m_data else None
                        item_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
                        records.append(
                            build_canonical_record(
                                source_slug=self.store_slug,
                                source_type="telecom",
                                store_name="Cellcard Cambodia Mobile",
                                item_id=f"cell_live_{item_slug}",
                                name=name,
                                price=price,
                                currency="USD",
                                category_native="Mobile Prepaid > 5G/4G Data",
                                package_size=pkg_size,
                                url=CELLCARD_MOBILE_URL,
                                scrape_date=ds,
                                attrs={"validity": m_val.group(1) if m_val else None},
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
