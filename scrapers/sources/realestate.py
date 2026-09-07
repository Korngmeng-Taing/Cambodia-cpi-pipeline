from __future__ import annotations

import json
import re
import time
from typing import Any

import pendulum

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    THROTTLE_DELAY,
    _cffi_get,
    build_canonical_record,
    log,
)


# 12. Realestate.com.kh (Housing)
# ═══════════════════════════════════════════════════════════════════════════
REALESTATE_CATEGORIES = [
    ("Phnom Penh Rentals", "https://www.realestate.com.kh/rent/phnom-penh/"),
    ("Apartments For Rent", "https://www.realestate.com.kh/rent/apartment/"),
    ("Condos For Rent", "https://www.realestate.com.kh/rent/condo/"),
    ("Villas For Rent", "https://www.realestate.com.kh/rent/villa/"),
    ("Houses For Rent", "https://www.realestate.com.kh/rent/house/"),
]

REALESTATE_BASELINE = [
    {
        "id": "re_condo_tonle",
        "name": "Studio Condo for Rent at The Bridge, Tonle Bassac",
        "price": 380.00,
        "category": "Residential Rental > Condo",
        "bedrooms": 1,
        "area_m2": 38,
    },
    {
        "id": "re_apt_daunpenh",
        "name": "1-Bedroom Colonial Style Apartment near Riverside Daun Penh",
        "price": 420.00,
        "category": "Residential Rental > Apartment",
        "bedrooms": 1,
        "area_m2": 65,
    },
    {
        "id": "re_condo_chroy",
        "name": "2-Bedroom Riverfront Condo for Rent in Chroy Changvar",
        "price": 650.00,
        "category": "Residential Rental > Condo",
        "bedrooms": 2,
        "area_m2": 95,
    },
    {
        "id": "re_villa_chbarampov",
        "name": "4-Bedroom Modern Link Villa for Rent in Chbar Ampov",
        "price": 950.00,
        "category": "Residential Rental > Villa",
        "bedrooms": 4,
        "area_m2": 210,
    },
    {
        "id": "re_apt_bkk1",
        "name": "2-Bedroom Serviced Apartment in BKK1",
        "price": 850.00,
        "category": "Residential Rental > Apartment",
        "bedrooms": 2,
        "area_m2": 90,
    },
    {
        "id": "re_condo_sensok",
        "name": "1-Bedroom Modern Condo near AEON 2 Sen Sok",
        "price": 400.00,
        "category": "Residential Rental > Condo",
        "bedrooms": 1,
        "area_m2": 45,
    },
    {
        "id": "re_house_toulkork",
        "name": "3-Bedroom Townhouse for Rent in Toul Kork",
        "price": 700.00,
        "category": "Residential Rental > House",
        "bedrooms": 3,
        "area_m2": 150,
    },
    {
        "id": "re_villa_chamkarmon",
        "name": "5-Bedroom Luxury Villa in Chamkarmon",
        "price": 2500.00,
        "category": "Residential Rental > Villa",
        "bedrooms": 5,
        "area_m2": 350,
    },
]


class RealestateKhScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="realestate", source_type="realestate")

    def _fetch_category_live(
        self, cat_name: str, cat_url: str, ds: str
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not HAS_BS4:
            return records
        for attempt in range(1, 4):
            try:
                resp = _cffi_get(cat_url, timeout=35)
                if resp.status_code != 200:
                    return records
                soup = BeautifulSoup(resp.text, "html.parser")
                next_script = soup.find("script", id="__NEXT_DATA__")
                if next_script and next_script.string:
                    data = json.loads(next_script.string)
                    # BUG FIX: .get("key", {}) returns None (not {}) when
                    # JSON value is explicitly null, causing AttributeError.
                    cache = data.get("props", {}).get("pageProps", {}).get("cacheData") or {}
                    results = (cache.get("results") or {}).get("data", {}).get("results") or []
                    for p in results:
                        pid = p.get("id")
                        if not pid:
                            continue
                        price_str = p.get("displayRent") or p.get("displayPrice") or ""
                        m = re.search(r"([\d,]+(\.\d+)?)", price_str)
                        price = float(m.group(1).replace(",", "")) if m else None
                        if not price or price <= 0:
                            continue
                        headline = (
                            p.get("headline")
                            or p.get("titleImgAlt")
                            or f"{p.get('categoryName', 'Property')} in Phnom Penh"
                        )
                        addr = p.get("address") or "Phnom Penh"
                        p_url = (
                            f"https://www.realestate.com.kh{p.get('url')}"
                            if p.get("url")
                            else f"https://www.realestate.com.kh/rent/{pid}/"
                        )
                        specs = p.get("specifications") or {}
                        records.append(
                            build_canonical_record(
                                source_slug="realestate",
                                source_type="realestate",
                                store_name="Realestate.com.kh",
                                item_id=f"re_{pid}",
                                name=f"{headline} - {addr}".strip(" -"),
                                price=price,
                                currency="USD",
                                category_native=f"Residential Rental > {p.get('categoryName') or cat_name}",
                                url=p_url,
                                scrape_date=ds,
                                attrs={
                                    "address": addr,
                                    "category": p.get("categoryName"),
                                    "specs": specs,
                                    "latitude": p.get("addressLatitude"),
                                    "longitude": p.get("addressLongitude"),
                                },
                            )
                        )
                break
            except Exception as exc:
                if attempt < 3:
                    log.warning(
                        "Realestate live scrape attempt %d failed for %s (%s), retrying in %ds...",
                        attempt,
                        cat_name,
                        exc,
                        attempt * 2,
                    )
                    time.sleep(attempt * 2)
                else:
                    log.warning(
                        "Realestate live scrape failed for %s after 3 attempts: %s",
                        cat_name,
                        exc,
                    )
        return records

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        seen_ids = set()

        for cat_name, cat_url in REALESTATE_CATEGORIES:
            cat_records = self._fetch_category_live(cat_name, cat_url, ds)
            for rec in cat_records:
                if rec["item_id"] not in seen_ids:
                    seen_ids.add(rec["item_id"])
                    records.append(rec)
            time.sleep(THROTTLE_DELAY)

        if not records:
            log.warning("Realestate live returned 0 items, using baseline catalog")
            for rental in REALESTATE_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug="realestate",
                        source_type="realestate",
                        store_name="Realestate.com.kh",
                        item_id=rental["id"],
                        name=rental["name"],
                        price=rental["price"],
                        currency="USD",
                        category_native=rental["category"],
                        attrs={
                            "bedrooms": rental.get("bedrooms"),
                            "area_m2": rental.get("area_m2"),
                        },
                        url="https://www.realestate.com.kh/rent/",
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )
        return records
