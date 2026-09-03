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


# 3. Delishop Cambodia — REST API v2 (Grocery)
# ═══════════════════════════════════════════════════════════════════════════
DELI_API = "https://api.delishop.asia/api/v2/products"
DELI_PAGE_SIZE = 100


class DelishopScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="delishop", source_type="grocery")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        page = 1
        max_page_retries = 3
        while True:
            body = None
            for attempt in range(1, max_page_retries + 1):
                try:
                    resp = _cffi_get(
                        DELI_API,
                        params={"page": page, "limit": DELI_PAGE_SIZE},
                        headers={
                            "Origin": "https://delishop.asia",
                            "Referer": "https://delishop.asia/",
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    break
                except Exception as e:
                    log.warning(
                        "Delishop page %d attempt %d/%d error: %s",
                        page,
                        attempt,
                        max_page_retries,
                        e,
                    )
                    if attempt < max_page_retries:
                        time.sleep(2 * attempt)
                    else:
                        if page > 1:
                            raise RuntimeError(
                                f"Delishop scrape failed mid-pagination on page {page} after {len(records)} items: {e}"
                            ) from e
                        break

            if not body:
                break
            products = body.get("data") or body.get("products") or []
            if not products:
                break
            for p in products:
                if not isinstance(p, dict):
                    continue
                price = _to_float(p.get("price"))
                if price is None:
                    continue
                cat_raw = p.get("category")
                subcat_raw = p.get("subcategory")
                cat_name = cat_raw.get("name") if isinstance(cat_raw, dict) else cat_raw
                subcat_name = (
                    subcat_raw.get("name")
                    if isinstance(subcat_raw, dict)
                    else subcat_raw
                )
                if cat_name and subcat_name and cat_name != subcat_name:
                    cat_full = f"{cat_name} > {subcat_name}"
                else:
                    cat_full = (
                        cat_name or subcat_name or p.get("categoryName") or "Grocery"
                    )
                records.append(
                    build_canonical_record(
                        source_slug="delishop",
                        source_type="grocery",
                        store_name="Delishop Cambodia",
                        item_id=str(p.get("id", "")),
                        name=p.get("name") or "",
                        price=price,
                        currency=p.get("currency") or "USD",
                        original_price=_to_float(
                            p.get("original_price") or p.get("originalPrice")
                        ),
                        barcode=p.get("barCode") or p.get("barcode"),
                        brand=p.get("brand"),
                        category_native=cat_full,
                        package_size=p.get("package_size")
                        or p.get("quantity")
                        or p.get("weight"),
                        url=p.get("url")
                        or f"https://delishop.asia/product/{p.get('id')}",
                        image_url=p.get("image")
                        or p.get("image_url")
                        or p.get("imageResized"),
                        scrape_date=ds,
                        on_promo=_to_float(
                            p.get("original_price") or p.get("originalPrice")
                        )
                        is not None
                        and (
                            _to_float(p.get("original_price") or p.get("originalPrice"))
                            or 0
                        )
                        > price,
                    )
                )
            if len(products) < DELI_PAGE_SIZE:
                break
            page += 1
            time.sleep(THROTTLE_DELAY)
        if not records:
            raise RuntimeError(f"Delishop: 0 products scraped on {ds}")
        return records
