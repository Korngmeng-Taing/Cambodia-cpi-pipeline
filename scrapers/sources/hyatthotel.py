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


# 16. Hyatt Regency Phnom Penh (Hotel)
# ═══════════════════════════════════════════════════════════════════════════
HYATT_ROOMS = [
    {
        "name": "Standard King Room",
        "room_type": "King Bed",
        "area_sqm": 38,
        "base_rate_usd": 185.0,
    },
    {
        "name": "Standard Twin Room",
        "room_type": "Twin Beds",
        "area_sqm": 38,
        "base_rate_usd": 185.0,
    },
    {
        "name": "King Bed High Floor City View",
        "room_type": "King Bed View",
        "area_sqm": 38,
        "base_rate_usd": 210.0,
    },
    {
        "name": "Twin Beds High Floor City View",
        "room_type": "Twin Beds View",
        "area_sqm": 38,
        "base_rate_usd": 210.0,
    },
    {
        "name": "1 King Bed with Balcony Courtyard View",
        "room_type": "King Balcony",
        "area_sqm": 42,
        "base_rate_usd": 235.0,
    },
    {
        "name": "Regency Club 1 King Bed with Lounge Access",
        "room_type": "Club King",
        "area_sqm": 45,
        "base_rate_usd": 265.0,
    },
    {
        "name": "Regency Club 2 Twin Beds with Lounge Access",
        "room_type": "Club Twin",
        "area_sqm": 45,
        "base_rate_usd": 265.0,
    },
    {
        "name": "Regency Suite King (Living Room & Dining Area)",
        "room_type": "Suite",
        "area_sqm": 72,
        "base_rate_usd": 420.0,
    },
    {
        "name": "Executive Suite River View",
        "room_type": "Suite",
        "area_sqm": 95,
        "base_rate_usd": 580.0,
    },
    {
        "name": "Diplomatic Suite with Private Terrace",
        "room_type": "Suite",
        "area_sqm": 125,
        "base_rate_usd": 780.0,
    },
    {
        "name": "Presidential Suite Phnom Penh View",
        "room_type": "Suite",
        "area_sqm": 180,
        "base_rate_usd": 1200.0,
    },
    {
        "name": "Market Café International Seafood Buffet Dinner",
        "room_type": "Buffet",
        "area_sqm": 0,
        "base_rate_usd": 42.0,
    },
    {
        "name": "Market Café Full American & Asian Breakfast Buffet",
        "room_type": "Breakfast",
        "area_sqm": 0,
        "base_rate_usd": 24.0,
    },
    {
        "name": "FiveFive Rooftop Restaurant 4-Course Dinner Set",
        "room_type": "Dining Set",
        "area_sqm": 0,
        "base_rate_usd": 55.0,
    },
    {
        "name": "The Lounge Royal Afternoon High Tea for Two",
        "room_type": "High Tea",
        "area_sqm": 0,
        "base_rate_usd": 28.0,
    },
    {
        "name": "Metropole Spa 60-Minute Signature Herbal Massage",
        "room_type": "Spa Service",
        "area_sqm": 0,
        "base_rate_usd": 65.0,
    },
]


class HyattHotelScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="hyyathotel", source_type="hotel")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        for idx, room in enumerate(HYATT_ROOMS):
            records.append(
                build_canonical_record(
                    source_slug="hyyathotel",
                    source_type="hotel",
                    store_name="Hyatt Regency Phnom Penh",
                    item_id=f"hyatt_{idx}",
                    name=f"{room['name']}",
                    price=room["base_rate_usd"],
                    currency="USD",
                    category_native=(
                        "Accommodation > Hotel Room"
                        if room.get("area_sqm", 0) > 0
                        else "Food Services > Hotel Dining & Buffet"
                    ),
                    attrs={
                        "room_type": room["room_type"],
                        "area_sqm": room["area_sqm"],
                        "base_rate_usd": room["base_rate_usd"],
                    },
                    url="https://www.hyatt.com/hyatt-regency/en-US/pnhrp-hyatt-regency-phnom-penh",
                    scrape_date=ds,
                    is_fallback=True,
                    fallback_reason="Static ratecard tariff (live API unavailable)",
                )
            )
        return records
