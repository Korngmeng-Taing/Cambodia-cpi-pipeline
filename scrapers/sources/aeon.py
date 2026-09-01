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


# 1. AEON 1 Phnom Penh — Next.js Proxy REST API (Grocery)
# ═══════════════════════════════════════════════════════════════════════════
AEON1_API = (
    "https://aeononlineshopping.com/api/proxy/stores/aeon1-aeon-phnom-penh/products"
)
AEON1_PAGE_SIZE = 100


def _build_aeon_category_map(filters: dict) -> dict[int, str]:
    """Flattens the nested AEON category tree into {cat_id: 'Parent > Child > Sub'} map."""
    cat_map = {}

    def _traverse(node: dict, path: list[str]):
        name = node.get("name") or ""
        cur_path = path + [name] if name else path
        node_id = node.get("id")
        if node_id:
            cat_map[node_id] = " > ".join(cur_path)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _traverse(child, cur_path)

    for root in (filters.get("categories") if isinstance(filters, dict) else []):
        if isinstance(root, dict):
            _traverse(root, [])
    return cat_map


AEON_MAX_PAGES = int(os.environ.get("AEON_MAX_PAGES", "0"))


AEON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Origin": "https://aeononlineshopping.com",
    "Referer": "https://aeononlineshopping.com/",
    "x-language": "en-gb",
    "x-currency": "KHR",
}


class AeonSupermarketScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="aeon", source_type="grocery")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        page = 1
        total_pages = 999
        cat_map: dict[int, str] = {}
        consecutive_page_errors = 0
        while page <= total_pages:
            if AEON_MAX_PAGES > 0 and page > AEON_MAX_PAGES:
                break
            body = None
            for attempt in range(5):
                try:
                    resp = _cffi_get(
                        AEON1_API,
                        params={"page": page, "limit": AEON1_PAGE_SIZE},
                        headers=AEON_HEADERS,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    break
                except Exception as exc:
                    if attempt < 4:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        log.warning("AEON1 page %d error after 5 retries: %s", page, exc)
            if not body:
                consecutive_page_errors += 1
                if consecutive_page_errors >= 3:
                    log.error("AEON1: 3 consecutive page failures, stopping at page %d", page)
                    break
                page += 1
                time.sleep(2.0)
                continue
            consecutive_page_errors = 0
            if not cat_map and isinstance(body.get("filters"), dict):
                cat_map = _build_aeon_category_map(body["filters"])

            prod_obj = body.get("products", {})
            if isinstance(prod_obj, dict):
                products = prod_obj.get("data", [])
                meta = prod_obj.get("meta", {})
                tp = meta.get("totalPages")
                if tp is None:
                    tp = prod_obj.get("lastPage")
                if tp is not None:
                    total_pages = tp
            elif isinstance(prod_obj, list):
                products = prod_obj
                total_pages = body.get("totalPages", page)
            else:
                products = body.get("data", [])

            if not products:
                break

            for p in products:
                if not isinstance(p, dict):
                    continue
                price = _to_float(p.get("salePrice") or p.get("price"))
                if price is None:
                    continue
                orig = _to_float(
                    p.get("fullPriceBeforeDiscount") or p.get("originalPrice")
                )
                on_sale = bool(p.get("discount") or (orig and orig > price))
                cat_id = (
                    p.get("categoryId") or p.get("departmentId") or p.get("divisionId")
                )
                cat_name = (
                    cat_map.get(cat_id)
                    or p.get("categoryName")
                    or p.get("category")
                    or "Grocery"
                )
                records.append(
                    build_canonical_record(
                        source_slug="aeon",
                        source_type="grocery",
                        store_name="AEON 1 Phnom Penh",
                        item_id=str(p.get("id", "")),
                        name=p.get("name") or p.get("title") or "",
                        price=price,
                        currency="KHR",
                        original_price=orig,
                        barcode=p.get("barcode"),
                        brand=p.get("brand"),
                        category_native=cat_name,
                        package_size=p.get("size") or p.get("quantity"),
                        url=p.get("url")
                        or f"https://aeononlineshopping.com/product/{p.get('id')}",
                        image_url=p.get("image")
                        or p.get("imageUrl")
                        or (
                            (p.get("galleries") or [{}])[0].get("url")
                            if p.get("galleries")
                            else None
                        ),
                        scrape_date=ds,
                        on_promo=on_sale,
                        attrs={"badges": p.get("badges") or []},
                    )
                )
            if len(products) < AEON1_PAGE_SIZE:
                break
            page += 1
            time.sleep(THROTTLE_DELAY)
        if not records:
            raise RuntimeError(f"AEON1: 0 products scraped on {ds}")
        return records


# ═══════════════════════════════════════════════════════════════════════════
# 2. AEON 3 Mean Chey — Next.js Proxy REST API (Fashion & Beauty)
# ═══════════════════════════════════════════════════════════════════════════
AEON3_API = (
    "https://aeononlineshopping.com/api/proxy/stores/aeon3-fashion-beauty/products"
)
AEON3_PAGE_SIZE = 100


class AeonFashionScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="aeon3", source_type="fashion")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        page = 1
        total_pages = 999
        cat_map: dict[int, str] = {}
        consecutive_page_errors = 0
        while page <= total_pages:
            if AEON_MAX_PAGES > 0 and page > AEON_MAX_PAGES:
                break
            body = None
            for attempt in range(5):
                try:
                    resp = _cffi_get(
                        AEON3_API,
                        params={"page": page, "limit": AEON3_PAGE_SIZE},
                        headers=AEON_HEADERS,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    break
                except Exception as exc:
                    if attempt < 4:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        log.warning("AEON3 page %d error after 5 retries: %s", page, exc)
            if not body:
                consecutive_page_errors += 1
                if consecutive_page_errors >= 3:
                    log.error("AEON3: 3 consecutive page failures, stopping at page %d", page)
                    break
                page += 1
                time.sleep(2.0)
                continue
            consecutive_page_errors = 0
            if not cat_map and isinstance(body.get("filters"), dict):
                cat_map = _build_aeon_category_map(body["filters"])

            prod_obj = body.get("products", {})
            if isinstance(prod_obj, dict):
                products = prod_obj.get("data", [])
                meta = prod_obj.get("meta", {})
                tp = meta.get("totalPages")
                if tp is None:
                    tp = prod_obj.get("lastPage")
                if tp is not None:
                    total_pages = tp
            elif isinstance(prod_obj, list):
                products = prod_obj
                total_pages = body.get("totalPages", page)
            else:
                products = body.get("data", [])

            for p in products:
                if not isinstance(p, dict):
                    continue
                price = _to_float(p.get("salePrice") or p.get("price"))
                if price is None:
                    continue
                orig = _to_float(
                    p.get("fullPriceBeforeDiscount") or p.get("originalPrice")
                )
                on_sale = bool(p.get("discount") or (orig and orig > price))
                cat_id = (
                    p.get("categoryId") or p.get("departmentId") or p.get("divisionId")
                )
                cat_name = (
                    cat_map.get(cat_id)
                    or p.get("categoryName")
                    or p.get("category")
                    or "Fashion & Beauty"
                )
                records.append(
                    build_canonical_record(
                        source_slug="aeon3",
                        source_type="fashion",
                        store_name="AEON 3 Mean Chey",
                        item_id=str(p.get("id", "")),
                        name=p.get("name") or p.get("title") or "",
                        price=price,
                        currency="KHR",
                        original_price=orig,
                        barcode=p.get("barcode"),
                        brand=p.get("brand"),
                        category_native=cat_name,
                        url=f"https://aeononlineshopping.com/product/{p.get('id')}",
                        image_url=p.get("image")
                        or p.get("imageUrl")
                        or (
                            (p.get("galleries") or [{}])[0].get("url")
                            if p.get("galleries")
                            else None
                        ),
                        scrape_date=ds,
                        on_promo=on_sale,
                    )
                )
            if len(products) < AEON3_PAGE_SIZE:
                break
            page += 1
            time.sleep(THROTTLE_DELAY)
        if not records:
            raise RuntimeError(f"AEON3: 0 products scraped on {ds}")
        return records
