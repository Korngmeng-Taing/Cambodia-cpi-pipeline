"""
scrapers/sources/khmermoto.py
──────────────────────────────
Scraper for Khmer Moto Shop (https://www.khmermotoshop.com/)
Covers COICOP Division 07 (Transport):
  • 07.1.2: Motorcycles & Scooters (Honda, Yamaha, Suzuki, Vespa, KTM, etc.)
  • 07.2.1: Motorcycle Helmets, Accessories & Spare Parts
  • 07.2.2: Motorcycle Lubricants & Engine Oil

Data Source: Public REST API via system.anakutapp.com (store_code=KMT)
"""

from __future__ import annotations

import re
import time
from typing import Any

import pendulum
import requests

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    THROTTLE_DELAY,
    build_canonical_record,
    log,
)

KHMER_MOTO_BASE_URL = "https://system.anakutapp.com/ecommerce/public/api/products"
KHMER_MOTO_STORE_CODE = "KMT"

CATEGORY_MAP = {
    21653: "Honda",
    21912: "Suzuki",
    21911: "Yamaha",
    21918: "Motorcycles",
    21919: "Electric Motors",
    21935: "TUK TUK",
    21934: "Bicycles",
    21920: "Helmet",
    21922: "Riding Gear",
    21923: "Accessories",
    21924: "Auto Parts",
    21921: "Lubricants",
    21925: "Services",
}

# Reliable offline fallback baseline in case of upstream network or API failure
KHMER_MOTO_BASELINE = [
    {
        "id": "kmt_honda_dream_125",
        "name": "Honda Dream 125cc",
        "price": 2980.0,
        "brand": "Honda",
        "category": "Motorcycles > Honda",
        "package_size": "125cc",
        "code": "KMT-HD-125",
    },
    {
        "id": "kmt_honda_wave_110",
        "name": "Honda Wave 110cc",
        "price": 1850.0,
        "brand": "Honda",
        "category": "Motorcycles > Honda",
        "package_size": "110cc",
        "code": "KMT-HW-110",
    },
    {
        "id": "kmt_honda_scoopy_110",
        "name": "Honda Scoopy Prestige 110cc",
        "price": 2450.0,
        "brand": "Honda",
        "category": "Motorcycles > Honda",
        "package_size": "110cc",
        "code": "KMT-HS-110",
    },
    {
        "id": "kmt_yamaha_pg1",
        "name": "Yamaha PG-1 115cc",
        "price": 2900.0,
        "brand": "Yamaha",
        "category": "Motorcycles > Yamaha",
        "package_size": "115cc",
        "code": "KMT-YPG-115",
    },
    {
        "id": "kmt_suzuki_nex_110",
        "name": "Suzuki Nex II 110cc",
        "price": 1780.0,
        "brand": "Suzuki",
        "category": "Motorcycles > Suzuki",
        "package_size": "110cc",
        "code": "KMT-SN-110",
    },
    {
        "id": "kmt_vespa_s_125",
        "name": "Vespa S 125cc",
        "price": 4939.0,
        "brand": "Vespa",
        "category": "Motorcycles > Vespa",
        "package_size": "125cc",
        "code": "KMT-VS-125",
    },
]


class KhmerMotoShopScraper(BaseScraper):
    """Scraper for Khmer Moto Shop retail motorbikes, gear, and accessories."""

    source_slug = "khmermoto"
    source_type = "retail"
    store_name = "Khmer Moto Shop"

    def __init__(self, store_slug: str = "khmermoto", source_type: str = "retail"):
        super().__init__(store_slug=store_slug, source_type=source_type)

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        page = 1
        row_per_page = 100

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

        while True:
            params = {
                "store_code": KHMER_MOTO_STORE_CODE,
                "page": page,
                "row_per_page": row_per_page,
            }
            try:
                resp = requests.get(
                    KHMER_MOTO_BASE_URL,
                    params=params,
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                log.warning("KhmerMotoShop page %d fetch failed: %s", page, exc)
                break

            items = payload.get("data", [])
            if not items or not isinstance(items, list):
                break

            for item in items:
                raw_name = (item.get("name") or "").strip()
                if not raw_name:
                    continue

                raw_price = item.get("price") or ""
                p_num = re.sub(r"[^\d.]", "", str(raw_price))
                try:
                    price = float(p_num) if p_num else 0.0
                except (ValueError, TypeError):
                    price = 0.0

                # Skip items with 0 price (out of stock or unpriced inquiry items)
                if price <= 0.0:
                    continue

                cat_id = item.get("category_id")
                category_name = CATEGORY_MAP.get(cat_id, "Motorcycles & Accessories")

                # Infer brand from title or category
                brand = None
                for candidate_brand in ("Honda", "Yamaha", "Suzuki", "Vespa", "BMW", "KTM", "Kawasaki", "Ducati", "Bajaj", "Keeway", "CFMOTO", "SHAD", "Vega", "Axor", "MASONTEX"):
                    if candidate_brand.lower() in raw_name.lower():
                        brand = candidate_brand
                        break
                if not brand and category_name in ("Honda", "Yamaha", "Suzuki"):
                    brand = category_name

                # Extract engine displacement if present (e.g. 125cc, 150cc, 160cc)
                cc_match = re.search(r"\b(\d{2,4}\s*cc)\b", raw_name, re.IGNORECASE)
                package_size = cc_match.group(1).replace(" ", "").lower() if cc_match else None

                item_id = str(item.get("id") or item.get("code") or raw_name)
                product_url = f"https://www.khmermotoshop.com/product/{item.get('id')}" if item.get("id") else "https://www.khmermotoshop.com/"

                records.append(
                    build_canonical_record(
                        source_slug=self.source_slug,
                        source_type=self.source_type,
                        store_name=self.store_name,
                        item_id=item_id,
                        name=raw_name,
                        price=price,
                        currency="USD",
                        barcode=item.get("code"),
                        brand=brand,
                        category_native=f"Vehicles > {category_name}",
                        package_size=package_size,
                        url=product_url,
                        image_url=item.get("image"),
                        scrape_date=ds,
                        attrs={
                            "product_code": item.get("code"),
                            "category_id": cat_id,
                            "raw_price_str": raw_price,
                        },
                    )
                )

            last_page = payload.get("last_page", 1)
            if page >= last_page:
                break
            page += 1
            time.sleep(THROTTLE_DELAY)

        if not records:
            log.warning("KhmerMotoShop returned 0 records; falling back to curated baseline catalog.")
            for fallback_item in KHMER_MOTO_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug=self.source_slug,
                        source_type=self.source_type,
                        store_name=self.store_name,
                        item_id=fallback_item["id"],
                        name=fallback_item["name"],
                        price=fallback_item["price"],
                        currency="USD",
                        brand=fallback_item["brand"],
                        category_native=f"Vehicles > {fallback_item['category']}",
                        package_size=fallback_item.get("package_size"),
                        barcode=fallback_item.get("code"),
                        url="https://www.khmermotoshop.com/",
                        scrape_date=ds,
                        is_fallback=True,
                        fallback_reason="Upstream API unavailable; using curated baseline",
                    )
                )

        log.info("KhmerMotoShop scraped %d valid product records for %s", len(records), ds)
        return records