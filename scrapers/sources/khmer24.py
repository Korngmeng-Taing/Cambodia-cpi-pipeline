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


# 11. Khmer24 Real Estate (Housing)
# ═══════════════════════════════════════════════════════════════════════════
KHMER24_CATEGORIES = [
    ("House For Rent", "https://www.khmer24.com/en/c-house-for-rent.html"),
    ("Apartment For Rent", "https://www.khmer24.com/en/c-apartment-for-rent.html"),
    ("Room For Rent", "https://www.khmer24.com/en/c-room-for-rent.html"),
    ("Land For Rent", "https://www.khmer24.com/en/c-land-for-rent.html"),
]

KHMER24_BASELINE_RENTALS = [
    {
        "id": "k24_condo_bkk1",
        "name": "1-Bedroom Modern Serviced Condo for Rent in BKK1",
        "price": 550.00,
        "category": "Residential Rental > Condo For Rent",
        "bedrooms": 1,
        "area_m2": 55,
    },
    {
        "id": "k24_apt_toulkork",
        "name": "2-Bedroom Fully Furnished Apartment in Toul Kork",
        "price": 450.00,
        "category": "Residential Rental > Apartment For Rent",
        "bedrooms": 2,
        "area_m2": 80,
    },
    {
        "id": "k24_house_chamkarmon",
        "name": "3-Bedroom Townhouse for Rent in Chamkarmon",
        "price": 800.00,
        "category": "Residential Rental > House For Rent",
        "bedrooms": 3,
        "area_m2": 120,
    },
    {
        "id": "k24_villa_sen_sok",
        "name": "4-Bedroom Twin Villa for Rent in Borey Peng Huoth Sen Sok",
        "price": 1200.00,
        "category": "Residential Rental > Villa For Rent",
        "bedrooms": 4,
        "area_m2": 240,
    },
    {
        "id": "k24_studio_daunpenh",
        "name": "Modern Studio Apartment near Riverside Daun Penh",
        "price": 350.00,
        "category": "Residential Rental > Apartment For Rent",
        "bedrooms": 1,
        "area_m2": 42,
    },
    {
        "id": "k24_condo_tonle",
        "name": "2-Bedroom High Floor Condo at Tonle Bassac",
        "price": 750.00,
        "category": "Residential Rental > Condo For Rent",
        "bedrooms": 2,
        "area_m2": 90,
    },
    {
        "id": "k24_house_chbarampov",
        "name": "4-Bedroom Link House in Chbar Ampov",
        "price": 600.00,
        "category": "Residential Rental > House For Rent",
        "bedrooms": 4,
        "area_m2": 180,
    },
    {
        "id": "k24_room_russeykeo",
        "name": "Single Room with Private Bathroom in Russey Keo",
        "price": 120.00,
        "category": "Residential Rental > Room For Rent",
        "bedrooms": 1,
        "area_m2": 25,
    },
]


class Khmer24Scraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="khmer24", source_type="realestate")

    def _fetch_category_live(
        self, cat_name: str, cat_url: str, ds: str
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not HAS_BS4:
            return records
        try:
            resp = _cffi_get(cat_url, timeout=15)
            if resp.status_code != 200:
                return records
            soup = BeautifulSoup(resp.text, "html.parser")
            seen_urls = set()
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if "adid-" in href and href not in seen_urls:
                    seen_urls.add(href)
                    txt = a.get_text(separator=" | ", strip=True)
                    m_price = re.search(r"\$\s*([\d,]+(\.\d+)?)", txt)
                    m_id = re.search(r"adid-(\d+)", href)
                    if m_price and m_id:
                        price = _to_float(m_price.group(1).replace(",", ""))
                        if price and price > 0:
                            item_id = m_id.group(1)
                            parts = [p.strip() for p in txt.split("|") if p.strip()]
                            clean_title = "Rental Property"
                            for p in parts:
                                if len(p) > 5 and not re.match(r"^\d+$", p) and "Verified" not in p and "$" not in p:
                                    clean_title = p
                                    break
                            records.append(
                                build_canonical_record(
                                    source_slug="khmer24",
                                    source_type="realestate",
                                    store_name="Khmer24 Real Estate",
                                    item_id=f"k24_{item_id}",
                                    name=clean_title,
                                    price=price,
                                    currency="USD",
                                    category_native=f"Residential Rental > {cat_name}",
                                    url=(
                                        href
                                        if href.startswith("http")
                                        else f"https://www.khmer24.com{href}"
                                    ),
                                    scrape_date=ds,
                                )
                            )
        except Exception as exc:
            log.warning("Khmer24 live scrape failed for %s: %s", cat_name, exc)
        return records

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        for cat_name, cat_url in KHMER24_CATEGORIES:
            cat_records = self._fetch_category_live(cat_name, cat_url, ds)
            records.extend(cat_records)
            time.sleep(THROTTLE_DELAY)

        if not records:
            log.warning("Khmer24 live returned 0 items, using baseline catalog")
            for rental in KHMER24_BASELINE_RENTALS:
                records.append(
                    build_canonical_record(
                        source_slug="khmer24",
                        source_type="realestate",
                        store_name="Khmer24 Real Estate",
                        item_id=rental["id"],
                        name=rental["name"],
                        price=rental["price"],
                        currency="USD",
                        category_native=rental["category"],
                        attrs={
                            "bedrooms": rental.get("bedrooms"),
                            "area_m2": rental.get("area_m2"),
                        },
                        url="https://www.khmer24.com/c-house-for-rent",
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )
        return records
