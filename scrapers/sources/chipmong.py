from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import pendulum
import requests

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

# 23. Chip Mong Supermarket Eden (GrabMart Cambodia)
# ===========================================================================
DEFAULT_CHIPMONG_URL = (
    "https://mart.grab.com/kh/en/merchant/chip-mong-supermarket-eden/10-C7CGVPK3TJ3AEX"
)
CHIPMONG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CHIPMONG_BASELINE = [
    {
        "id": "CHIPMONG_JASMINE_RICE",
        "name": "Chip Mong Premium Jasmine Rice 5kg",
        "price": 19500.0,
        "currency": "KHR",
        "brand": "Chip Mong",
        "category": "Rice & Grains",
    },
    {
        "id": "CHIPMONG_COOKING_OIL",
        "name": "Healthy Chef Cooking Oil 1L",
        "price": 18200.0,
        "currency": "KHR",
        "brand": "Healthy Chef",
        "category": "Cooking Essentials",
    },
    {
        "id": "CHIPMONG_FRESH_EGGS",
        "name": "Fresh Farm Eggs 10s",
        "price": 7800.0,
        "currency": "KHR",
        "brand": "Fresh Farm",
        "category": "Eggs & Dairy",
    },
    {
        "id": "CHIPMONG_SARDINES",
        "name": "Yummi Cook Sardines in Tomato Sauce 240g",
        "price": 11230.0,
        "currency": "KHR",
        "brand": "Yummi Cook",
        "category": "Canned Foods",
    },
    {
        "id": "CHIPMONG_FRESH_MILK",
        "name": "Anchor Pure Milk 1L",
        "price": 8900.0,
        "currency": "KHR",
        "brand": "Anchor",
        "category": "Eggs & Dairy",
    },
]


class GrabChipMongSupermarketScraper(BaseScraper):
    """
    Scraper for Chip Mong Supermarket Eden on GrabMart Cambodia.
    Extracts Next.js SSR embedded catalog data (__NEXT_DATA__) with department and item hierarchies.
    """

    def __init__(self, target_url: str | None = None, session: requests.Session | None = None):
        super().__init__(store_slug="grab_chipmong", source_type="grocery")
        self.target_url = target_url or os.environ.get("CHIPMONG_GRAB_URL", DEFAULT_CHIPMONG_URL)
        self.session = session or requests.Session()
        self.session.headers.update(CHIPMONG_HEADERS)

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        merchant_data = None
        for attempt in range(4):
            try:
                if attempt > 0:
                    time.sleep(2.0 * attempt)
                resp = _cffi_get(self.target_url, headers=self.session.headers, timeout=30)
                resp.raise_for_status()
                html_text = resp.text

                data = None
                if HAS_BS4:
                    soup = BeautifulSoup(html_text, "html.parser")
                    script = soup.find("script", id="__NEXT_DATA__")
                    if script and script.string:
                        data = json.loads(script.string)
                if data is None:
                    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
                    if m:
                        data = json.loads(m.group(1))

                if data:
                    preloaded = (
                        data.get("props", {})
                        .get("pageProps", {})
                        .get("preloadedState", {})
                    )
                    queries = preloaded.get("merchantApi", {}).get("queries", {})
                    for qv in queries.values():
                        if isinstance(qv, dict) and "merchant" in qv.get("data", {}):
                            merchant_data = qv["data"]["merchant"]
                            break
                if merchant_data:
                    break
            except Exception as exc:
                log.warning("GrabMart Chip Mong attempt %d error: %s", attempt + 1, exc)

        if merchant_data:
            try:
                store_name = merchant_data.get("name") or "Chip Mong Supermarket Eden"
                currency = merchant_data.get("currency", {}).get("code", "KHR")
                departments = merchant_data.get("menu", {}).get("departments", [])

                seen_ids = set()
                for dept in departments:
                    dept_name = dept.get("name") or "Grocery"
                    for it in dept.get("items", []):
                        if not isinstance(it, dict):
                            continue
                        iid = it.get("ID")
                        if not iid or iid in seen_ids:
                            continue
                        seen_ids.add(iid)

                        name = it.get("name") or ""
                        price_minor = it.get("priceInMinorUnit")
                        price = (float(price_minor) / 100.0) if price_minor is not None else None
                        if price is None:
                            p_display = (it.get("priceV2") or {}).get("amountDisplay")
                            price = _to_float(p_display)
                        if price is None:
                            continue

                        barcode = it.get("barcode")
                        sku = it.get("SKU")
                        brand = name.split(" - ")[0].strip() if " - " in name else None
                        img_url = it.get("imgHref") or (
                            (it.get("images") or [None])[0] if it.get("images") else None
                        )

                        records.append(
                            build_canonical_record(
                                source_slug=self.store_slug,
                                source_type=self.source_type,
                                store_name=store_name,
                                item_id=str(iid),
                                name=name,
                                price=price,
                                currency=currency,
                                barcode=barcode,
                                brand=brand,
                                category_native=dept_name,
                                url=self.target_url,
                                image_url=img_url,
                                scrape_date=ds,
                                attrs={
                                    "sku": sku,
                                    "merchant_id": it.get("merchantID"),
                                    "item_class_id": it.get("itemClassID"),
                                },
                            )
                        )
            except Exception as parse_err:
                log.warning("GrabMart Chip Mong item normalization failed: %s", parse_err)

        if not records:
            log.warning("GrabMart Chip Mong live parse returned 0 records; falling back to baseline catalog.")
            for item in CHIPMONG_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type=self.source_type,
                        store_name="Chip Mong Supermarket Eden",
                        item_id=item["id"],
                        name=item["name"],
                        price=item["price"],
                        currency=item.get("currency", "KHR"),
                        brand=item.get("brand"),
                        category_native=item.get("category", "Grocery"),
                        url=self.target_url,
                        scrape_date=ds,
                        is_fallback=True,
                        fallback_reason="baseline_catalog",
                    )
                )

        return records
