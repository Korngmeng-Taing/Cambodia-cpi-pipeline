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


# 4. L192 Marketplace — GraphQL API & Baseline Matrix (Retail)
# ═══════════════════════════════════════════════════════════════════════════
L192_GQL_URL = "https://graph-fs.l192.com/graphql"
L192_PAGE_SIZE = 50
L192_MAX_PAGES = int(os.environ.get("L192_MAX_PAGES", "20"))

L192_BASELINE_PRODUCTS = [
    {
        "id": "l192_101",
        "name": "Men's Casual Cotton Polo T-Shirt",
        "price": 8.50,
        "brand": "L192 Basic",
        "category": "Fashion & Apparel > Men's Clothing",
        "size": "L",
    },
    {
        "id": "l192_102",
        "name": "Women's Floral Summer Maxi Dress",
        "price": 12.00,
        "brand": "Sweet Look",
        "category": "Fashion & Apparel > Women's Clothing",
        "size": "M",
    },
    {
        "id": "l192_103",
        "name": "Stainless Steel Electric Kettle 1.8L",
        "price": 7.50,
        "brand": "Camel",
        "category": "Home Appliances > Kitchenware",
        "size": "1.8L",
    },
    {
        "id": "l192_104",
        "name": "Non-Stick Granite Frying Pan 28cm",
        "price": 9.90,
        "brand": "Cookmaster",
        "category": "Home & Living > Cookware",
        "size": "28cm",
    },
    {
        "id": "l192_105",
        "name": "Wireless Bluetooth Earbuds Pro",
        "price": 11.50,
        "brand": "Awei",
        "category": "Consumer Electronics > Audio",
        "size": "1 unit",
    },
    {
        "id": "l192_106",
        "name": "Foldable Storage Box 66L Fabric Organizer",
        "price": 5.20,
        "brand": "HomeStyle",
        "category": "Home & Living > Storage & Organization",
        "size": "66L",
    },
    {
        "id": "l192_107",
        "name": "Unisex Canvas Low Top Casual Sneakers",
        "price": 14.00,
        "brand": "SportFlex",
        "category": "Clothing & Footwear > Shoes",
        "size": "EU 41",
    },
    {
        "id": "l192_108",
        "name": "Rechargeable LED Desk Lamp with Eye Protection",
        "price": 6.80,
        "brand": "Baseus",
        "category": "Home & Living > Lighting",
        "size": "1 unit",
    },
]


class L192Scraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="l192", source_type="retail")

    def _fetch_live(self) -> list[dict[str, Any]]:
        query = """
        query productSearch(
          $filter: ProductSearchFilter
          $limit: Int
          $offset: Int
        ) {
          productSearch(filter: $filter, offset: $offset, limit: $limit) {
            items {
              id
              title
              code
              keyword
              price
              price_before_discount
              discount_percentage
              stock
            }
          }
        }
        """
        all_items: list[dict[str, Any]] = []
        page_idx = 0
        max_pages = L192_MAX_PAGES if L192_MAX_PAGES > 0 else 100
        consecutive_errors = 0

        while page_idx < max_pages:
            offset = page_idx * L192_PAGE_SIZE
            payload = {
                "query": query,
                "variables": {
                    "filter": {"categoryId": 0},
                    "offset": offset,
                    "limit": L192_PAGE_SIZE,
                },
                "operationName": "productSearch",
            }
            try:
                resp = _cffi_post(
                    L192_GQL_URL,
                    json=payload,
                    headers={"Content-Type": "application/json", "x-lang": "en"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    batch = (
                        resp.json()
                        .get("data", {})
                        .get("productSearch", {})
                        .get("items")
                        or []
                    )
                    if not batch:
                        break
                    all_items.extend(batch)
                    consecutive_errors = 0
                    if len(batch) < L192_PAGE_SIZE:
                        break
                else:
                    log.warning("L192 page %d returned HTTP %d", page_idx, resp.status_code)
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        break
            except Exception as e:
                log.warning("L192 page %d fetch failed: %s", page_idx, e)
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    break
            page_idx += 1
            time.sleep(THROTTLE_DELAY)
        return all_items

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        try:
            items = self._fetch_live()
            for item in items:
                price = _to_float(item.get("price"))
                if price is None or price <= 0:
                    continue
                item_id = str(item.get("id") or item.get("code") or "")
                records.append(
                    build_canonical_record(
                        source_slug="l192",
                        source_type="retail",
                        store_name="L192 Cambodia",
                        item_id=f"l192_{item_id}",
                        name=item.get("title") or f"L192 Retail Item {item_id}",
                        price=price,
                        currency="USD",
                        brand=item.get("brand_name") or "L192",
                        category_native="General Retail > Apparel & Household Goods",
                        url=f"https://www.l192.com/product/{item_id}",
                        scrape_date=ds,
                        attrs={
                            "item_code": item.get("code"),
                            "stock": item.get("stock"),
                            "discount_percentage": item.get("discount_percentage"),
                            "price_before_discount": item.get("price_before_discount"),
                        },
                    )
                )
        except Exception as exc:
            log.warning(
                "L192 live query failed: %s, falling back to baseline catalog", exc
            )

        if not records:
            for item in L192_BASELINE_PRODUCTS:
                # Fallback rows carry a distinct l192_fb_ id prefix: baseline
                # ids share the live item_id shape, so without the prefix they
                # merge into the same canonical items downstream and a long
                # live outage silently masquerades as real observations.
                raw_id = str(item["id"]).removeprefix("l192_")
                records.append(
                    build_canonical_record(
                        source_slug="l192",
                        source_type="retail",
                        store_name="L192 Cambodia",
                        item_id=f"l192_fb_{raw_id}",
                        name=item["name"],
                        price=item["price"],
                        currency="USD",
                        brand=item["brand"],
                        category_native=item["category"],
                        package_size=item.get("size"),
                        url=f"https://www.l192.com/product/{item['id']}",
                        scrape_date=ds,
                        is_fallback=True,
                        fallback_reason="live_fetch_failed_baseline_catalog",
                    )
                )
        return records
