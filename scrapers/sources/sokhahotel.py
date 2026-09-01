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


SOKHA_ROOMS = [
    {
        "id": "sokha_deluxe_city",
        "name": "Deluxe City View Room (1 Night)",
        "price": 105.00,
        "category": "Accommodation > Hotel Room",
        "room_type": "Deluxe City View",
        "area_sqm": 52,
    },
    {
        "id": "sokha_deluxe_river",
        "name": "Deluxe River View King Room (1 Night)",
        "price": 115.00,
        "category": "Accommodation > Hotel Room",
        "room_type": "Deluxe River View",
        "area_sqm": 52,
    },
    {
        "id": "sokha_premier_twin",
        "name": "Premier River View Twin Room (1 Night)",
        "price": 135.00,
        "category": "Accommodation > Hotel Room",
        "room_type": "Premier Twin",
        "area_sqm": 52,
    },
    {
        "id": "sokha_premier_king",
        "name": "Premier River View King Room (1 Night)",
        "price": 140.00,
        "category": "Accommodation > Hotel Room",
        "room_type": "Premier King",
        "area_sqm": 52,
    },
    {
        "id": "sokha_club_room",
        "name": "Club King Room with Lounge Access (1 Night)",
        "price": 165.00,
        "category": "Accommodation > Club Floor",
        "room_type": "Club King",
        "area_sqm": 52,
    },
    {
        "id": "sokha_club_suite",
        "name": "Club Suite with Executive Lounge (1 Night)",
        "price": 195.00,
        "category": "Accommodation > Suite",
        "room_type": "Club Suite",
        "area_sqm": 85,
    },
    {
        "id": "sokha_junior_suite",
        "name": "Junior Suite Riverfront View (1 Night)",
        "price": 220.00,
        "category": "Accommodation > Suite",
        "room_type": "Junior Suite",
        "area_sqm": 75,
    },
    {
        "id": "sokha_exec_suite",
        "name": "Executive Riverfront Suite (1 Night)",
        "price": 280.00,
        "category": "Accommodation > Suite",
        "room_type": "Executive Suite",
        "area_sqm": 110,
    },
    {
        "id": "sokha_mekong_suite",
        "name": "Mekong Royal Suite 2-Bedroom (1 Night)",
        "price": 450.00,
        "category": "Accommodation > Luxury Suite",
        "room_type": "Royal Suite",
        "area_sqm": 170,
    },
    {
        "id": "sokha_presidential_suite",
        "name": "Presidential Penthouse Suite (1 Night)",
        "price": 850.00,
        "category": "Accommodation > Presidential Suite",
        "room_type": "Presidential",
        "area_sqm": 290,
    },
    {
        "id": "sokha_villa_2bed",
        "name": "2-Bedroom Riverside Luxury Villa (1 Night)",
        "price": 520.00,
        "category": "Accommodation > Villa",
        "room_type": "Villa",
        "area_sqm": 220,
    },
    {
        "id": "sokha_lotus_buffet",
        "name": "Lotus Restaurant International Dinner Buffet",
        "price": 28.00,
        "category": "Food Services > Hotel Dining & Buffet",
        "room_type": "Dining Buffet",
        "area_sqm": 0,
    },
    {
        "id": "sokha_breakfast_buffet",
        "name": "Tonle Sap International Breakfast Buffet",
        "price": 16.00,
        "category": "Food Services > Hotel Dining & Buffet",
        "room_type": "Breakfast Buffet",
        "area_sqm": 0,
    },
    {
        "id": "sokha_high_tea",
        "name": "Champa Lounge Afternoon High Tea Set for Two",
        "price": 22.00,
        "category": "Food Services > Afternoon Tea",
        "room_type": "High Tea",
        "area_sqm": 0,
    },
    {
        "id": "sokha_spa_aroma",
        "name": "Jasmine Spa 60-Minute Aromatherapy Body Massage",
        "price": 45.00,
        "category": "Personal Care > Spa & Wellness",
        "room_type": "Spa Service",
        "area_sqm": 0,
    },
    {
        "id": "sokha_fitness_daypass",
        "name": "Sokha Health Club & Swimming Pool Day Pass",
        "price": 15.00,
        "category": "Recreation & Culture > Sports & Fitness",
        "room_type": "Day Pass",
        "area_sqm": 0,
    },
]


class SokhaHotelScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="sokhahotel", source_type="hotel")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        for room in SOKHA_ROOMS:
            records.append(
                build_canonical_record(
                    source_slug="sokhahotel",
                    source_type="hotel",
                    store_name="Sokha Phnom Penh Hotel",
                    item_id=room["id"],
                    name=room["name"],
                    price=room["price"],
                    currency="USD",
                    category_native=room["category"],
                    attrs={
                        "room_type": room["room_type"],
                        "area_sqm": room["area_sqm"],
                    },
                    url="https://www.sokhahotels.com.kh/phnompenh/",
                    scrape_date=ds,
                    is_fallback=True,
                )
            )
        return records
