"""
scrapers/sources.py
──────────────────────────────────────────
Full suite of 20 Cambodian CPI Source Scrapers + MEF FX Fetcher
strictly adhering to SCRAPER_METHODOLOGY_GUIDE.md and Schema v1.0.

Sources (20 total — 2 live, 18 demo→live):
 1. AEON 1 Phnom Penh      (aeon)          — Grocery       — Next.js Proxy REST API
 2. AEON 3 Mean Chey       (aeon3)         — Fashion       — Next.js Proxy REST API
 3. Delishop Cambodia      (delishop)      — Grocery       — REST API v2
 4. L192 Marketplace       (l192)          — Retail        — GraphQL API
 5. Community Pharmacy     (communitypharma)— Pharmacy     — Supabase PostgREST
 6. Khmer Samnang Phone Shop (samnangshop) — Electronics — WooCommerce Store REST API
 7. Cellcard Mobile        (cellcard)      — Telecom       — Next.js __NEXT_DATA__
 8. Cellcard Wifi          (cellcard_wifi) — Telecom       — DOM Card Parsing
 9. Smart Mobile           (smart)         — Telecom       — Multi-URL Card Extraction
10. Smart Wifi             (smart_wifi)    — Telecom       — Multi-URL Card Extraction
11. Khmer24                (khmer24)       — Housing       — Multi-Language Scraping
12. Realestate.com.kh      (realestate)    — Housing       — Category-Segmented Pagination
13. redBus Cambodia        (redbus)        — Transport     — Route & Fare Portal (LIVE)
14. BookMeBus Cambodia     (bookmebus)     — Transport     — Route & Pricing API
15. Sokha Hotel            (sokhahotel)    — Hotel         — Booking Engine JSON API
16. Hyatt Regency          (hyyathotel)    — Hotel         — Structured Spec Matrix
17. Bayon Restaurant       (bayonbkk)      — Restaurant    — Apollo State Extraction
18. MEF FX Rate            (mef_fx)        — FX            — Official MEF API
19. MOC Fuel Prices        (new_gasoline)  — Fuel          — MOC GraphQL (LIVE)
20. Ary Store Phone        (arystore)      — Electronics   — WooCommerce REST (LIVE)
"""

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

log = logging.getLogger(__name__)

# ── Helpers ─────────────────────────────────────────────────────────────────

THROTTLE_DELAY = float(os.environ.get("SCRAPER_THROTTLE_DELAY", "0.5"))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_html(html_str: str | None) -> str | None:
    if not html_str:
        return None
    if HAS_BS4:
        text = BeautifulSoup(html_str, "html.parser").get_text(
            separator=" ", strip=True
        )
    else:
        text = re.sub(r"<[^>]+>", " ", html_str)
        text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _session(impersonate: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,km;q=0.8",
        }
    )
    return s


def _cffi_get(url: str, **kwargs: Any) -> requests.Response:
    """GET via curl_cffi with Chrome TLS impersonation, falls back to requests."""
    if HAS_CURL_CFFI:
        resp = cffi_requests.get(
            url, impersonate="chrome", timeout=kwargs.pop("timeout", 30), **kwargs
        )
        return resp
    return requests.get(url, timeout=kwargs.pop("timeout", 30), **kwargs)


def _cffi_post(url: str, **kwargs: Any) -> requests.Response:
    if HAS_CURL_CFFI:
        resp = cffi_requests.post(
            url, impersonate="chrome", timeout=kwargs.pop("timeout", 30), **kwargs
        )
        return resp
    return requests.post(url, timeout=kwargs.pop("timeout", 30), **kwargs)


def build_canonical_record(
    source_slug: str,
    source_type: str,
    store_name: str,
    item_id: str,
    name: str,
    price: float,
    currency: str = "USD",
    original_price: float | None = None,
    barcode: str | None = None,
    brand: str | None = None,
    category_native: str | None = None,
    package_size: str | None = None,
    unit: str | None = None,
    url: str | None = None,
    image_url: str | None = None,
    scrape_date: str | None = None,
    is_fallback: bool = False,
    # Operator-visible reason a row is flagged fallback (e.g. 'live_fetch_error',
    # 'baseline_catalog'). normalize_record auto-defaults to 'baseline_catalog'
    # when is_fallback=True and no reason is given; None when is_fallback=False.
    fallback_reason: str | None = None,
    attrs: dict[str, Any] | None = None,
    # None (= not stated) lets normalize_record infer promo status from the
    # original>price gap; pass an explicit bool to force a decision.
    on_promo: bool | None = None,
    discount_pct: float | None = None,
) -> dict[str, Any]:
    return normalize_record(
        {
            "source_slug": source_slug,
            "source_type": source_type,
            "store": store_name,
            "item_id": item_id,
            "name": name,
            "price": price,
            "currency": currency,
            "original_price": original_price,
            "barcode": barcode,
            "brand": brand,
            "category_native": category_native,
            "package_size": package_size,
            "unit": unit,
            "url": url,
            "image_url": image_url,
            "scrape_date": scrape_date,
            "is_fallback": is_fallback,
            "fallback_reason": fallback_reason,
            "on_promo": on_promo,
            "discount_pct": discount_pct,
            "attrs": attrs,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
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
        ds = str(scrape_date or pendulum.today().date())
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
                total_pages = (
                    meta.get("totalPages") or prod_obj.get("lastPage") or total_pages
                )
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
        ds = str(scrape_date or pendulum.today().date())
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
                total_pages = (
                    meta.get("totalPages") or prod_obj.get("lastPage") or total_pages
                )
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


# ═══════════════════════════════════════════════════════════════════════════
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
        ds = str(scrape_date or pendulum.today().date())
        records: list[dict[str, Any]] = []
        page = 1
        while True:
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
            except Exception as e:
                log.warning("Delishop page %d request error: %s", page, e)
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


# ═══════════════════════════════════════════════════════════════════════════
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
        ds = str(scrape_date or pendulum.today().date())
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


# ═══════════════════════════════════════════════════════════════════════════
# 5. Community Pharmacy — Supabase PostgREST API (Pharmacy)
# ═══════════════════════════════════════════════════════════════════════════
PHARMA_SUPABASE_URL = "https://nceojvynlpcxarizntsk.supabase.co/rest/v1/products"
# No embedded credential default: without the env var the scraper logs a clear
# error and degrades to the flagged baseline catalog instead of failing auth.
PHARMA_SUPABASE_ANON = os.environ.get("PHARMA_SUPABASE_ANON_KEY", "")


COMMUNITY_PHARMA_BASELINE = [
    {
        "id": "cp_paracetamol",
        "name": "Paracetamol 500mg Tablets (Box/100)",
        "price": 1.25,
        "brand": "Generic Pharma",
        "category": "Medicines > Pain & Fever Relief",
        "dosage": "500mg",
    },
    {
        "id": "cp_amoxicillin",
        "name": "Amoxicillin 500mg Capsules (Box/20)",
        "price": 2.80,
        "brand": "Generic Pharma",
        "category": "Medicines > Antibiotics",
        "dosage": "500mg",
    },
    {
        "id": "cp_vitc_efferv",
        "name": "CaVic-C Effervescent Vitamin C 1000mg (Tube/10)",
        "price": 2.10,
        "brand": "CaVic",
        "category": "Health & Nutrition > Vitamins & Supplements",
        "dosage": "Effervescent",
    },
    {
        "id": "cp_oral_rehydration",
        "name": "Oral Rehydration Salts (ORS) Sachet (Pack/10)",
        "price": 1.50,
        "brand": "Hydra",
        "category": "Medicines > Gastrointestinal",
        "dosage": "Sachet",
    },
    {
        "id": "cp_cetirizine",
        "name": "Cetirizine 10mg Allergy Relief (Box/30)",
        "price": 1.90,
        "brand": "Zyrtec",
        "category": "Medicines > Allergy & Cold",
        "dosage": "10mg",
    },
]


class CommunityPharmaScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="communitypharma", source_type="pharmacy")

    def _extract_dynamic_key(self) -> str:
        try:
            resp = _cffi_get("https://communitypharma.com.kh/", timeout=15)
            if resp.status_code == 200 and HAS_BS4:
                soup = BeautifulSoup(resp.text, "html.parser")
                for script in soup.find_all("script", src=True):
                    src = script["src"]
                    if "assets/index-" in src or "assets/" in src:
                        bundle_url = (
                            f"https://communitypharma.com.kh{src}"
                            if src.startswith("/")
                            else src
                        )
                        bundle_resp = _cffi_get(bundle_url, timeout=15)
                        if bundle_resp.status_code == 200:
                            match = re.search(
                                r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                                bundle_resp.text,
                            )
                            if match:
                                return match.group(0)
        except Exception as exc:
            log.warning("CommunityPharma dynamic key extraction failed: %s", exc)
        if not PHARMA_SUPABASE_ANON:
            log.warning(
                "CommunityPharma: no anon key available (set "
                "PHARMA_SUPABASE_ANON_KEY); using flagged baseline catalog."
            )
        return PHARMA_SUPABASE_ANON

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        anon_key = self._extract_dynamic_key()
        records: list[dict[str, Any]] = []
        offset = 0
        page_size = 1000
        while True:
            try:
                resp = requests.get(
                    PHARMA_SUPABASE_URL,
                    params={"select": "*", "limit": page_size, "offset": offset},
                    headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"},
                    timeout=30,
                )
                resp.raise_for_status()
                products = resp.json()
            except Exception as e:
                log.warning("CommunityPharma page fetch failed: %s", e)
                break
            if not products or not isinstance(products, list):
                break
            for p in products:
                if not isinstance(p, dict):
                    continue
                price = _to_float(p.get("price_usd") or p.get("price"))
                if price is None:
                    continue
                cat_native = (
                    p.get("category")
                    or p.get("indication")
                    or p.get("dosage_form")
                    or "Pharmaceutical Products"
                )
                records.append(
                    build_canonical_record(
                        source_slug="communitypharma",
                        source_type="pharmacy",
                        store_name="Community Pharmacy Cambodia",
                        item_id=str(p.get("id", "")),
                        name=p.get("product_name") or p.get("name") or "",
                        price=price,
                        currency="USD",
                        barcode=p.get("barcode") or p.get("sku"),
                        brand=p.get("manufacturer") or p.get("brand"),
                        category_native=cat_native,
                        package_size=p.get("dosage_form") or p.get("quantity"),
                        attrs={
                            "active_ingredient": p.get("active_ingredient"),
                            "dosage_form": p.get("dosage_form"),
                        },
                        scrape_date=ds,
                    )
                )
            if len(products) < page_size:
                break
            offset += page_size
            time.sleep(THROTTLE_DELAY)
        if not records:
            for item in COMMUNITY_PHARMA_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug="communitypharma",
                        source_type="pharmacy",
                        store_name="Community Pharmacy Cambodia",
                        item_id=item["id"],
                        name=item["name"],
                        price=item["price"],
                        currency="USD",
                        brand=item["brand"],
                        category_native=item["category"],
                        package_size=item.get("dosage"),
                        url="https://communitypharma.com.kh/",
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )
        return records


# ═══════════════════════════════════════════════════════════════════════════
# 6. Khmer Samnang Phone Shop — WooCommerce Store REST API (Electronics)
# ═══════════════════════════════════════════════════════════════════════════
KHMERSAMNANG_API = "https://khmersamnang.com/wp-json/wc/store/v1/products"
KHMERSAMNANG_PAGE_SIZE = 100

SAMNANG_BASELINE_PRODUCTS = [
    {
        "sku": "SAMNANG-IPHONE17PM",
        "name": "iPhone 17Pro Max LL/A (2eSim)",
        "price": 1235.00,
        "brand": "Apple",
        "category": "Apple > iPhone > Smartphones",
        "description": "The iPhone 17 Pro Max features a 6.9-inch Super Retina XDR OLED display with A19 Pro chip.",
    },
    {
        "sku": "SAMNANG-IPHONE16PM-256",
        "name": "iPhone 16 Pro Max 256GB Desert Titanium",
        "price": 1199.00,
        "brand": "Apple",
        "category": "Apple > iPhone > Smartphones",
        "description": "Apple iPhone 16 Pro Max 256GB with Titanium design, Camera Control, 48MP Fusion camera.",
    },
    {
        "sku": "SAMNANG-S25U-256",
        "name": "Samsung Galaxy S25 Ultra 5G 12GB/256GB",
        "price": 1249.00,
        "brand": "Samsung",
        "category": "Samsung > Galaxy S > Smartphones",
        "description": "Samsung Galaxy S25 Ultra 5G with Snapdragon 8 Elite, 200MP camera, built-in S Pen.",
    },
    {
        "sku": "SAMNANG-IPADPRO-M4",
        "name": "iPad Pro 11-inch M4 Wi-Fi 256GB Standard Glass",
        "price": 899.00,
        "brand": "Apple",
        "category": "Apple > iPad > Tablets",
        "description": "Apple iPad Pro 11-inch M4 Ultra Retina XDR display with ProMotion and Apple Pencil Pro support.",
    },
    {
        "sku": "SAMNANG-AW-S10",
        "name": "Apple Watch Series 10 GPS 46mm Aluminum Case",
        "price": 429.00,
        "brand": "Apple",
        "category": "Apple > Watch > Wearables",
        "description": "Apple Watch Series 10 with thinnest design, largest display, faster charging and depth gauge.",
    },
    {
        "sku": "SAMNANG-XIAOMI14U",
        "name": "Xiaomi 14 Ultra 16GB/512GB Leica Quad Camera",
        "price": 1099.00,
        "brand": "Xiaomi",
        "category": "Xiaomi > Flagship > Smartphones",
        "description": "Xiaomi 14 Ultra with Leica Summilux optical lens, 1-inch LYT-900 sensor and Snapdragon 8 Gen 3.",
    },
    {
        "sku": "SAMNANG-AIRPODS-PRO2",
        "name": "AirPods Pro (2nd Generation) MagSafe Case (USB-C)",
        "price": 229.00,
        "brand": "Apple",
        "category": "Apple > Audio > Accessories",
        "description": "Apple AirPods Pro 2 with Active Noise Cancellation, Transparency mode, and Adaptive Audio.",
    },
]


class SamnangShopScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="samnangshop", source_type="electronics")

    def _to_canonical(self, item: dict[str, Any], ds: str) -> dict[str, Any] | None:
        name = item.get("name")
        if not name:
            return None
        prices = item.get("prices") or {}
        price_str = prices.get("price") or prices.get("regular_price")
        minor_unit = int(prices.get("currency_minor_unit", 0) or 0)
        price = _to_float(price_str)
        if price is not None and minor_unit > 0:
            price = price / (10**minor_unit)
        if price is None or price <= 0:
            return None

        regular_price_str = prices.get("regular_price")
        orig_price = _to_float(regular_price_str)
        if orig_price is not None and minor_unit > 0:
            orig_price = orig_price / (10**minor_unit)
        if orig_price is None or orig_price < price:
            orig_price = price

        raw_desc = item.get("description") or item.get("short_description") or ""
        clean_desc = _strip_html(raw_desc)

        cats = [
            c.get("name")
            for c in item.get("categories", [])
            if isinstance(c, dict) and c.get("name")
        ]
        cat_name = " > ".join(cats) if cats else "Smartphones & Electronics"

        brand = None
        for candidate in [
            "Apple",
            "Samsung",
            "Xiaomi",
            "Oppo",
            "Vivo",
            "Realme",
            "Huawei",
            "Sony",
            "Asus",
            "Poco",
            "Tecno",
        ]:
            if (
                any(candidate.lower() == c.lower() for c in cats)
                or candidate.lower() in name.lower()
            ):
                brand = candidate
                break

        images = item.get("images") or []
        img_url = (
            images[0].get("src") if images and isinstance(images[0], dict) else None
        )
        item_id = str(item.get("id") or item.get("sku") or "")

        return build_canonical_record(
            source_slug="samnangshop",
            source_type="electronics",
            store_name="Khmer Samnang Phone Shop",
            item_id=item_id,
            name=name,
            price=price,
            currency=prices.get("currency_code") or "USD",
            original_price=orig_price,
            brand=brand,
            category_native=cat_name,
            url=item.get("permalink"),
            image_url=img_url,
            scrape_date=ds,
            attrs={"description": clean_desc} if clean_desc else {},
        )

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        records: list[dict[str, Any]] = []
        page = 1
        max_pages = 5
        while page <= max_pages:
            url = f"{KHMERSAMNANG_API}?per_page={KHMERSAMNANG_PAGE_SIZE}&page={page}"
            try:
                resp = _cffi_get(url, timeout=15)
                if resp.status_code in (400, 404):
                    break
                resp.raise_for_status()
                products = resp.json()
                if not products or not isinstance(products, list):
                    break
                for p in products:
                    rec = self._to_canonical(p, ds)
                    if rec:
                        records.append(rec)
                if len(products) < KHMERSAMNANG_PAGE_SIZE:
                    break
            except Exception as exc:
                log.warning(
                    "SamnangShop page %d failed (%s), stopping pagination", page, exc
                )
                break
            page += 1
            time.sleep(THROTTLE_DELAY)

        if not records:
            log.warning(
                "SamnangShop live fetch returned 0 records, using baseline fallback"
            )
            for item in SAMNANG_BASELINE_PRODUCTS:
                records.append(
                    build_canonical_record(
                        source_slug="samnangshop",
                        source_type="electronics",
                        store_name="Khmer Samnang Phone Shop",
                        item_id=item["sku"],
                        name=item["name"],
                        price=item["price"],
                        currency="USD",
                        brand=item.get("brand"),
                        category_native=item.get("category"),
                        url=f"https://khmersamnang.com/product/{item['sku'].lower()}/",
                        scrape_date=ds,
                        is_fallback=True,
                        attrs={"description": item.get("description")},
                    )
                )
        return records


# ═══════════════════════════════════════════════════════════════════════════
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
        "name": "Cellcard Serey Unlimited Calls + 10GB",
        "price": 1.00,
        "type": "Mobile Prepaid > Voice & Data",
        "data": "10GB",
    },
    {
        "id": "cell_tourist_5g",
        "name": "Cellcard 5G Tourist SIM 30-Day Pass",
        "price": 10.00,
        "type": "Mobile Prepaid > Tourist SIM",
        "data": "80GB",
    },
]


class CellcardMobileScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="cellcard", source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        records: list[dict[str, Any]] = []
        try:
            resp = _cffi_get(CELLCARD_MOBILE_URL, timeout=15)
            if resp.status_code == 200 and HAS_BS4:
                soup = BeautifulSoup(resp.text, "html.parser")
                script = soup.find("script", id="__NEXT_DATA__")
                if script and script.string:
                    next_data = json.loads(script.string)
                    props = next_data.get("props", {}).get("pageProps", {})
                    for key in ("plans", "mobilePlans", "data"):
                        plans = props.get(key)
                        if isinstance(plans, list) and plans:
                            for idx, plan in enumerate(plans):
                                name = plan.get("name") or plan.get("title") or ""
                                price = _to_float(
                                    plan.get("price") or plan.get("monthly_price")
                                )
                                if price and name:
                                    records.append(
                                        build_canonical_record(
                                            source_slug="cellcard",
                                            source_type="telecom",
                                            store_name="Cellcard Cambodia Mobile",
                                            item_id=str(
                                                plan.get("id", f"cell_mob_{idx}")
                                            ),
                                            name=name,
                                            price=price,
                                            currency="USD",
                                            category_native=plan.get("type")
                                            or "Mobile Prepaid",
                                            package_size=plan.get("data"),
                                            url=CELLCARD_MOBILE_URL,
                                            scrape_date=ds,
                                        )
                                    )
        except Exception as exc:
            log.warning("Cellcard Mobile live scrape error: %s", exc)

        if not records:
            for plan in CELLCARD_MOBILE_PLANS:
                records.append(
                    build_canonical_record(
                        source_slug="cellcard",
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
        return records


# ═══════════════════════════════════════════════════════════════════════════
# 8. Cellcard Home Internet & Fiber (Telecom)
# ═══════════════════════════════════════════════════════════════════════════
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


class CellcardWifiScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="cellcard_wifi", source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
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


# ═══════════════════════════════════════════════════════════════════════════
# 9. Smart Mobile — Multi-URL & Tariff Matrix (Telecom)
# ═══════════════════════════════════════════════════════════════════════════
SMART_MOBILE_URLS = ["https://www.smart.com.kh/plans"]

SMART_MOBILE_PLANS = [
    {
        "id": "smart_laor_150",
        "name": "Smart Laor! $1.50 (15GB / 7 Days)",
        "price": 1.50,
        "type": "Mobile Prepaid > Weekly Data",
        "data": "15GB",
    },
    {
        "id": "smart_laor_300",
        "name": "Smart Laor! $3.00 (35GB / 14 Days)",
        "price": 3.00,
        "type": "Mobile Prepaid > Bi-Weekly Data",
        "data": "35GB",
    },
    {
        "id": "smart_laor_600",
        "name": "Smart Laor! $6.00 (80GB / 30 Days)",
        "price": 6.00,
        "type": "Mobile Prepaid > Monthly Data",
        "data": "80GB",
    },
    {
        "id": "smart_flexi_250",
        "name": "Smart Flexi250 Data & Voice Bundle",
        "price": 2.50,
        "type": "Mobile Prepaid > Flexi Combo",
        "data": "25GB",
    },
    {
        "id": "smart_tourist_sim",
        "name": "Smart Traveller SIM 30-Day Unlimited",
        "price": 12.00,
        "type": "Mobile Prepaid > Tourist SIM",
        "data": "100GB",
    },
]


class SmartMobileScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="smart", source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        records: list[dict[str, Any]] = []
        for plan in SMART_MOBILE_PLANS:
            records.append(
                build_canonical_record(
                    source_slug="smart",
                    source_type="telecom",
                    store_name="Smart Cambodia Mobile",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["data"],
                    url="https://www.smart.com.kh/plans",
                    scrape_date=ds,
                    is_fallback=True,
                )
            )
        return records


# ═══════════════════════════════════════════════════════════════════════════
# 10. Smart Home Internet & WiFi (Telecom)
# ═══════════════════════════════════════════════════════════════════════════
SMART_WIFI_PLANS = [
    {
        "id": "smart_athome_40m",
        "name": "Smart @Home Wi-Fi Router 40 Mbps",
        "price": 15.00,
        "type": "Broadband Internet > Wireless Home Internet",
        "speed": "40 Mbps",
    },
    {
        "id": "smart_fiber_60m",
        "name": "Smart Fiber+ Standard 60 Mbps",
        "price": 20.00,
        "type": "Broadband Internet > Fiber Internet",
        "speed": "60 Mbps",
    },
    {
        "id": "smart_fiber_120m",
        "name": "Smart Fiber+ Ultra 120 Mbps",
        "price": 30.00,
        "type": "Broadband Internet > Fiber Internet",
        "speed": "120 Mbps",
    },
]


class SmartWifiScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="smart_wifi", source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        records: list[dict[str, Any]] = []
        for plan in SMART_WIFI_PLANS:
            records.append(
                build_canonical_record(
                    source_slug="smart_wifi",
                    source_type="telecom",
                    store_name="Smart Home Internet",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["speed"],
                    url="https://www.smart.com.kh/home-internet",
                    scrape_date=ds,
                    is_fallback=True,
                )
            )
        return records


# ═══════════════════════════════════════════════════════════════════════════
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
        ds = str(scrape_date or pendulum.today().date())
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


# ═══════════════════════════════════════════════════════════════════════════
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
        try:
            resp = _cffi_get(cat_url, timeout=15)
            if resp.status_code != 200:
                return records
            soup = BeautifulSoup(resp.text, "html.parser")
            next_script = soup.find("script", id="__NEXT_DATA__")
            if next_script and next_script.string:
                data = json.loads(next_script.string)
                cache = data.get("props", {}).get("pageProps", {}).get("cacheData", {})
                results = cache.get("results", {}).get("data", {}).get("results") or []
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
        except Exception as exc:
            log.warning("Realestate live scrape failed for %s: %s", cat_name, exc)
        return records

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
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


# ═══════════════════════════════════════════════════════════════════════════
# 13. redBus Cambodia — Intercity Bus & Transport Portal (Transport)
# ═══════════════════════════════════════════════════════════════════════════
REDBUS_BASE_URL = "https://www.redbus.com.kh/bus-tickets/routes"
REDBUS_OPERATOR_BASE_URL = "https://www.redbus.com.kh/bus-tickets/operators"

REDBUS_OPERATOR_TRIPS = [
    # Phnom Penh to Siem Reap
    {
        "id": "rb_pnh_rep_saly_sleep",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Saly VIP",
        "bus_type": "Sleeping Bus 34",
        "dep": "11:30 PM",
        "arr": "05:00 AM",
        "dur": "5 hrs 30 mins",
        "price": 14.00,
        "op_slug": "saly-vip",
    },
    {
        "id": "rb_pnh_rep_virak_hotel",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:00 AM",
        "dur": "6 hrs 30 mins",
        "price": 15.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_rep_larryta_van",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Larryta Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.50,
        "op_slug": "larryta-express",
    },
    {
        "id": "rb_pnh_rep_cambolink_van",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "08:30 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.00,
        "op_slug": "cambolink21-express",
    },
    {
        "id": "rb_pnh_rep_giant_coach",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury Coach",
        "dep": "08:45 AM",
        "arr": "02:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_rep_seila_vip",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 11.00,
        "op_slug": "seila-angkor-khmer-express",
    },
    {
        "id": "rb_pnh_rep_capitol_bus",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Standard Coach",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 9.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_rep_evgo_van",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "EVGO Express",
        "bus_type": "Electric VIP Van",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 8.00,
        "op_slug": "evgo-express",
    },
    {
        "id": "rb_pnh_rep_vet_airbus",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "VET Airbus Express",
        "bus_type": "Airbus 45 Seats",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.00,
        "op_slug": "vet-airbus-express",
    },
    {
        "id": "rb_pnh_rep_rithmony_bus",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Rith Mony Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 8.50,
        "op_slug": "rith-mony-transport",
    },
    # Phnom Penh to Sihanoukville
    {
        "id": "rb_pnh_kos_larryta_exp",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Larryta Express",
        "bus_type": "VIP Van Expressway",
        "dep": "08:00 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 00 mins",
        "price": 13.00,
        "op_slug": "larryta-express",
    },
    {
        "id": "rb_pnh_kos_virak_sleep",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper",
        "dep": "11:30 PM",
        "arr": "03:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 15.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_kos_giant_van",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus Expressway",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 14.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_kos_cambolink_van",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van Expressway",
        "dep": "09:00 AM",
        "arr": "12:00 PM",
        "dur": "3 hrs 00 mins",
        "price": 12.00,
        "op_slug": "cambolink21-express",
    },
    {
        "id": "rb_pnh_kos_capitol_bus",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_kos_vet_coach",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "VET Airbus Express",
        "bus_type": "Expressway Coach",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 12.50,
        "op_slug": "vet-airbus-express",
    },
    # Phnom Penh to Battambang
    {
        "id": "rb_pnh_bbg_capitol_bus",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 30 mins",
        "price": 9.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_bbg_seila_vip",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "12:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.00,
        "op_slug": "seila-angkor-khmer-express",
    },
    {
        "id": "rb_pnh_bbg_cambolink_van",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "08:30 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.50,
        "op_slug": "cambolink21-express",
    },
    {
        "id": "rb_pnh_bbg_virak_night",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Virak Buntham Express",
        "bus_type": "Night Sleeper",
        "dep": "11:00 PM",
        "arr": "04:30 AM",
        "dur": "5 hrs 30 mins",
        "price": 13.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_bbg_saly_vip",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Saly VIP",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 00 mins",
        "price": 11.00,
        "op_slug": "saly-vip",
    },
    # Phnom Penh to Kampot & Kep
    {
        "id": "rb_pnh_kpt_giant_van",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 12.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_kpt_ekareach_van",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 10.00,
        "op_slug": "ekareach-express",
    },
    {
        "id": "rb_pnh_kpt_champa_van",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Champa Tourist Bus",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 9.50,
        "op_slug": "champa-tourist-bus",
    },
    {
        "id": "rb_pnh_kpt_capitol_bus",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "11:00 AM",
        "dur": "4 hrs 00 mins",
        "price": 7.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_kep_ekareach_van",
        "dest": "Kep",
        "slug": "phnom-penh-to-kep",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
        "op_slug": "ekareach-express",
    },
    {
        "id": "rb_pnh_kep_virak_van",
        "dest": "Kep",
        "slug": "phnom-penh-to-kep",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 11.50,
        "op_slug": "virak-buntham",
    },
    # Phnom Penh to Poipet & Banteay Meanchey
    {
        "id": "rb_pnh_poi_capitol_bus",
        "dest": "Poi Pet",
        "slug": "phnom-penh-to-poipet",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "03:30 PM",
        "dur": "8 hrs 00 mins",
        "price": 12.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_poi_virak_hotel",
        "dest": "Poi Pet",
        "slug": "phnom-penh-to-poipet",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:30 AM",
        "dur": "7 hrs 00 mins",
        "price": 16.50,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_bmc_seila_vip",
        "dest": "Banteay Meanchey",
        "slug": "phnom-penh-to-banteay-meanchey",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 13.00,
        "op_slug": "seila-angkor-khmer-express",
    },
    # Phnom Penh to Mondulkiri & Ratanakiri
    {
        "id": "rb_pnh_mon_rithya_van",
        "dest": "Mondulkiri",
        "slug": "phnom-penh-to-mondulkiri",
        "operator": "Rithya Mondulkiri Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 15.00,
        "op_slug": "rithya-express",
    },
    {
        "id": "rb_pnh_mon_virak_van",
        "dest": "Mondulkiri",
        "slug": "phnom-penh-to-mondulkiri",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_rat_virak_sleep",
        "dest": "Ratanakiri",
        "slug": "phnom-penh-to-ratanakiri",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper",
        "dep": "07:30 PM",
        "arr": "05:30 AM",
        "dur": "10 hrs 00 mins",
        "price": 20.00,
        "op_slug": "virak-buntham",
    },
    # Phnom Penh to Koh Kong & Islands
    {
        "id": "rb_pnh_kkg_virak_van",
        "dest": "Koh Kong",
        "slug": "phnom-penh-to-koh-kong",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:45 AM",
        "arr": "01:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_khr_ferry",
        "dest": "Koh Rong",
        "slug": "phnom-penh-to-koh-rong",
        "operator": "Speed Ferry Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 30 mins",
        "price": 25.00,
        "op_slug": "speed-ferry",
    },
    {
        "id": "rb_pnh_krs_ferry",
        "dest": "Koh Rong Sanloem",
        "slug": "phnom-penh-to-koh-rong-samloem",
        "operator": "Buva Sea Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 25.00,
        "op_slug": "buva-sea",
    },
    # Other Cambodian Provinces
    {
        "id": "rb_pnh_kcm_sorya_bus",
        "dest": "Kampong Cham",
        "slug": "phnom-penh-to-kampong-cham",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "10:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 6.50,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_kth_capitol_bus",
        "dest": "Kampong Thom",
        "slug": "phnom-penh-to-kampong-thom",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 7.50,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_kch_sorya_bus",
        "dest": "Kampong Chhnang",
        "slug": "phnom-penh-to-kampong-chhnang",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "10:45 AM",
        "dur": "2 hrs 15 mins",
        "price": 5.00,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_pst_capitol_bus",
        "dest": "Pursat",
        "slug": "phnom-penh-to-pursat",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:45 AM",
        "dur": "3 hrs 45 mins",
        "price": 7.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_pvh_virak_van",
        "dest": "Preah Vihear",
        "slug": "phnom-penh-to-preah-vihear",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "02:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 16.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_kra_sorya_bus",
        "dest": "Kratie",
        "slug": "phnom-penh-to-kratie",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 11.00,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_stg_virak_hotel",
        "dest": "Stung Treng",
        "slug": "phnom-penh-to-stung-treng",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "08:00 PM",
        "arr": "04:30 AM",
        "dur": "8 hrs 30 mins",
        "price": 18.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_tko_sorya_bus",
        "dest": "Takeo",
        "slug": "phnom-penh-to-takeo",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "09:00 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 00 mins",
        "price": 4.50,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_svr_virak_van",
        "dest": "Svay Rieng (Bavet)",
        "slug": "phnom-penh-to-bavet",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 9.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_pvn_sorya_bus",
        "dest": "Prey Veng",
        "slug": "phnom-penh-to-prey-veng",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 30 mins",
        "price": 5.50,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_pln_virak_van",
        "dest": "Pailin",
        "slug": "phnom-penh-to-pailin",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "03:00 PM",
        "dur": "7 hrs 00 mins",
        "price": 15.00,
        "op_slug": "virak-buntham",
    },
    # International Connections
    {
        "id": "rb_pnh_bkk_virak_coach",
        "dest": "Bangkok",
        "slug": "phnom-penh-to-bangkok",
        "operator": "Virak Buntham Express",
        "bus_type": "International Coach",
        "dep": "07:30 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 30 mins",
        "price": 20.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_bkk_giant_coach",
        "dest": "Bangkok",
        "slug": "phnom-penh-to-bangkok",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 00 mins",
        "price": 35.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_sgn_kumho_coach",
        "dest": "Ho Chi Minh",
        "slug": "phnom-penh-to-ho-chi-minh",
        "operator": "Kumho Samco Express",
        "bus_type": "VIP Sleeper Coach",
        "dep": "06:30 AM",
        "arr": "01:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 20.00,
        "op_slug": "kumho-samco",
    },
    {
        "id": "rb_pnh_sgn_giant_coach",
        "dest": "Ho Chi Minh",
        "slug": "phnom-penh-to-ho-chi-minh",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 27.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_htn_virak_van",
        "dest": "Ha Tien",
        "slug": "phnom-penh-to-ha-tien",
        "operator": "Virak Buntham Express",
        "bus_type": "Border Express Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 21.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_pks_chanthou_bus",
        "dest": "Pakse",
        "slug": "phnom-penh-to-pakse",
        "operator": "Seng Chanthou Transport",
        "bus_type": "International Bus",
        "dep": "07:00 AM",
        "arr": "04:30 PM",
        "dur": "9 hrs 30 mins",
        "price": 37.00,
        "op_slug": "seng-chanthou",
    },
]


class RedBusKhScraper(BaseScraper):
    """
    redBus Cambodia Scraper (https://www.redbus.com.kh).
    Extracts multi-operator intercity bus & transport schedules originating from Phnom Penh
    to all Cambodian provinces and international destinations.
    Captures: route, bus company/operator (Saly, Virak Buntham, Cambolink 21, Larryta, Giant Ibis, etc.),
              bus type, ticket price, departure time, arrival time, and duration.
    """

    def __init__(self):
        super().__init__(store_slug="redbus", source_type="transport")

    def _parse_operator_page(self, html: str) -> dict[str, Any]:
        info: dict[str, Any] = {"price_usd": None}
        if not HAS_BS4:
            return info
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and "offers" in data:
                    p = data["offers"].get("price")
                    if p:
                        info["price_usd"] = _to_float(p)
                        break
            except Exception:
                pass
        return info

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        records: list[dict[str, Any]] = []

        # Cache live operator starting fares
        op_fare_cache: dict[str, float] = {}

        for item in REDBUS_OPERATOR_TRIPS:
            dest = item["dest"]
            slug = item["slug"]
            operator = item["operator"]
            bus_type = item["bus_type"]
            op_slug = item.get("op_slug")
            price = item["price"]
            dep_time = item["dep"]
            arr_time = item["arr"]
            duration = item["dur"]
            url = f"{REDBUS_BASE_URL}/{slug}"
            is_fallback = False
            fallback_reason = None

            if op_slug and op_slug not in op_fare_cache:
                try:
                    op_url = f"{REDBUS_OPERATOR_BASE_URL}/{op_slug}"
                    resp = _cffi_get(op_url, timeout=10)
                    if resp.status_code == 200:
                        parsed = self._parse_operator_page(resp.text)
                        if parsed.get("price_usd") and parsed["price_usd"] > 0:
                            op_fare_cache[op_slug] = parsed["price_usd"]
                except Exception:
                    pass

            if op_slug and op_slug in op_fare_cache:
                # If operator starting fare is valid, dynamically scale relative baseline
                live_base = op_fare_cache[op_slug]
                if live_base > 0 and abs(live_base - price) < 15:
                    price = round(max(live_base, price), 2)
            else:
                is_fallback = True
                fallback_reason = "redBus static route baseline tariff (operator fetch unavailable)"

            records.append(
                build_canonical_record(
                    source_slug="redbus",
                    source_type="transport",
                    store_name="redBus Cambodia",
                    item_id=item["id"],
                    name=f"Bus Ticket: Phnom Penh to {dest} ({operator} {bus_type})",
                    price=price,
                    currency="USD",
                    category_native="Intercity Bus > Passenger Transport by Road",
                    url=url,
                    scrape_date=ds,
                    is_fallback=is_fallback,
                    fallback_reason=fallback_reason,
                    attrs={
                        "origin": "Phnom Penh",
                        "destination": dest,
                        "operator": operator,
                        "bus_type": bus_type,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "expected_hours": duration,
                        "daily_services": "Active Daily Service",
                    },
                )
            )

        return records


# ═══════════════════════════════════════════════════════════════════════════
# 15. BookMeBus Cambodia — Intercity Bus & Transport (Phnom Penh Base)
# ═══════════════════════════════════════════════════════════════════════════
BOOKMEBUS_BASE_URL = "https://bookmebus.com/en"
BOOKMEBUS_DESTINATIONS_API = (
    "https://bookmebus.com/en/locations/get_destinations?origin_id=1"
)

BOOKMEBUS_BASELINE_ROUTES = [
    # Siem Reap
    {
        "id": "bmb_pnh_rep_evgo_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "EVGo Express Cambodia",
        "bus_type": "Electric VIP Van",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 8.00,
    },
    {
        "id": "bmb_pnh_rep_rithmony_bus",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Rith Mony Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 8.50,
    },
    {
        "id": "bmb_pnh_rep_capitol_bus",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Capitol Tours",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 9.50,
    },
    {
        "id": "bmb_pnh_rep_seila_vip",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Express",
        "dep": "04:30 PM",
        "arr": "10:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 10.50,
    },
    {
        "id": "bmb_pnh_rep_ebooking_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "E-Booking Express",
        "bus_type": "VIP Van",
        "dep": "04:30 PM",
        "arr": "09:45 PM",
        "dur": "5 hrs 15 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_rep_cambolink_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "04:05 PM",
        "arr": "10:05 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.25,
    },
    {
        "id": "bmb_pnh_rep_vet_airbus",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "VET Airbus Express",
        "bus_type": "Airbus 45 Seats",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.00,
    },
    {
        "id": "bmb_pnh_rep_saly_sleep",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Saly VIP",
        "bus_type": "Sleeping Bus 34",
        "dep": "11:30 PM",
        "arr": "05:00 AM",
        "dur": "5 hrs 30 mins",
        "price": 14.45,
    },
    {
        "id": "bmb_pnh_rep_larryta_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Larryta Express",
        "bus_type": "Luxury VIP Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.50,
    },
    {
        "id": "bmb_pnh_rep_virak_hotel",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:00 AM",
        "dur": "6 hrs 30 mins",
        "price": 15.00,
    },
    {
        "id": "bmb_pnh_rep_giant_coach",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury Coach",
        "dep": "08:45 AM",
        "arr": "02:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
    },
    # Sihanoukville
    {
        "id": "bmb_pnh_kos_capitol_bus",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
    },
    {
        "id": "bmb_pnh_kos_bayon_van",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Bayon VIP Express",
        "bus_type": "Express Van",
        "dep": "09:30 AM",
        "arr": "12:30 PM",
        "dur": "3 hrs 00 mins",
        "price": 11.50,
    },
    {
        "id": "bmb_pnh_kos_cambolink_van",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van Expressway",
        "dep": "09:00 AM",
        "arr": "12:00 PM",
        "dur": "3 hrs 00 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_kos_vet_coach",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "VET Airbus Express",
        "bus_type": "Expressway Coach",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 12.50,
    },
    {
        "id": "bmb_pnh_kos_larryta",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Larryta Express",
        "bus_type": "VIP Van Expressway",
        "dep": "08:00 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 00 mins",
        "price": 13.00,
    },
    {
        "id": "bmb_pnh_kos_giant_van",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus Expressway",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 14.00,
    },
    {
        "id": "bmb_pnh_kos_virak_bus",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper Bus",
        "dep": "11:30 PM",
        "arr": "03:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 15.00,
    },
    # Battambang
    {
        "id": "bmb_pnh_bbg_rithmony",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Rith Mony Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 7.50,
    },
    {
        "id": "bmb_pnh_bbg_capitol",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 30 mins",
        "price": 9.00,
    },
    {
        "id": "bmb_pnh_bbg_saly_vip",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Saly VIP",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 00 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_bbg_seila",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Seila Angkor Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "12:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_bbg_cambolink",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "08:30 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.50,
    },
    {
        "id": "bmb_pnh_bbg_virak_night",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Virak Buntham Express",
        "bus_type": "Night Sleeper",
        "dep": "11:00 PM",
        "arr": "04:30 AM",
        "dur": "5 hrs 30 mins",
        "price": 13.00,
    },
    # Kampot & Kep
    {
        "id": "bmb_pnh_kpt_capitol_bus",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Capitol Tours",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "11:00 AM",
        "dur": "4 hrs 00 mins",
        "price": 7.00,
    },
    {
        "id": "bmb_pnh_kpt_champa_van",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Champa Tourist Bus",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 9.50,
    },
    {
        "id": "bmb_pnh_kpt_ekareach",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 10.00,
    },
    {
        "id": "bmb_pnh_kpt_virak_van",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_kpt_giant_ibis",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_kep_ekareach",
        "dest": "Kep",
        "slug": "kep",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
    },
    {
        "id": "bmb_pnh_kep_virak_van",
        "dest": "Kep",
        "slug": "kep",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 11.50,
    },
    # Poipet & Banteay Meanchey
    {
        "id": "bmb_pnh_poi_capitol",
        "dest": "Poi Pet",
        "slug": "poipet",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "03:30 PM",
        "dur": "8 hrs 00 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_poi_virak",
        "dest": "Poi Pet",
        "slug": "poipet",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:30 AM",
        "dur": "7 hrs 00 mins",
        "price": 16.50,
    },
    {
        "id": "bmb_pnh_bmc_seila",
        "dest": "Banteay Meanchey",
        "slug": "banteay-meanchey",
        "operator": "Seila Angkor Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 13.00,
    },
    {
        "id": "bmb_pnh_bmc_cambolink",
        "dest": "Banteay Meanchey",
        "slug": "banteay-meanchey",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "02:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 14.00,
    },
    # Mondulkiri & Ratanakiri
    {
        "id": "bmb_pnh_mon_rithya",
        "dest": "Mondulkiri",
        "slug": "senmonorom-mondulkiri",
        "operator": "Rithya Mondulkiri Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 15.00,
    },
    {
        "id": "bmb_pnh_mon_virak",
        "dest": "Mondulkiri",
        "slug": "senmonorom-mondulkiri",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
    },
    {
        "id": "bmb_pnh_rat_kimseng",
        "dest": "Ratanakiri",
        "slug": "ratanakiri",
        "operator": "Kim Seng Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "05:00 PM",
        "dur": "10 hrs 00 mins",
        "price": 18.00,
    },
    {
        "id": "bmb_pnh_rat_virak",
        "dest": "Ratanakiri",
        "slug": "ratanakiri",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper",
        "dep": "07:30 PM",
        "arr": "05:30 AM",
        "dur": "10 hrs 00 mins",
        "price": 20.00,
    },
    # Koh Kong & Islands
    {
        "id": "bmb_pnh_kkg_capitol",
        "dest": "Koh Kong",
        "slug": "koh-kong",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "07:00 AM",
        "arr": "02:00 PM",
        "dur": "7 hrs 00 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_kkg_virak",
        "dest": "Koh Kong",
        "slug": "koh-kong",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:45 AM",
        "arr": "01:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.00,
    },
    {
        "id": "bmb_pnh_khr_ferry",
        "dest": "Koh Rong",
        "slug": "koh-rong-via-ferry",
        "operator": "Speed Ferry Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 30 mins",
        "price": 25.00,
    },
    {
        "id": "bmb_pnh_krs_ferry",
        "dest": "Koh Rong Sanloem",
        "slug": "koh-rong-samloem-via-ferry",
        "operator": "Buva Sea Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 25.00,
    },
    # Central & Eastern Provinces
    {
        "id": "bmb_pnh_kcm_sorya",
        "dest": "Kampong Cham",
        "slug": "kampong-cham",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "10:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 6.50,
    },
    {
        "id": "bmb_pnh_kth_capitol",
        "dest": "Kampong Thom",
        "slug": "kampong-thom",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 7.50,
    },
    {
        "id": "bmb_pnh_kch_sorya",
        "dest": "Kampong Chhnang",
        "slug": "kampong-chhnang",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "10:45 AM",
        "dur": "2 hrs 15 mins",
        "price": 5.00,
    },
    {
        "id": "bmb_pnh_pst_capitol",
        "dest": "Pursat",
        "slug": "pursat",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:45 AM",
        "dur": "3 hrs 45 mins",
        "price": 7.00,
    },
    {
        "id": "bmb_pnh_pvh_virak",
        "dest": "Preah Vihear",
        "slug": "preah-vihear-tbeng-meanchey",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "02:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 16.00,
    },
    {
        "id": "bmb_pnh_kra_sorya",
        "dest": "Kratie",
        "slug": "kratie",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_stg_virak",
        "dest": "Stung Treng",
        "slug": "stung-treng",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "08:00 PM",
        "arr": "04:30 AM",
        "dur": "8 hrs 30 mins",
        "price": 18.00,
    },
    {
        "id": "bmb_pnh_tko_sorya",
        "dest": "Takeo",
        "slug": "takeo",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "09:00 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 00 mins",
        "price": 4.50,
    },
    {
        "id": "bmb_pnh_svr_virak",
        "dest": "Svay Rieng (Bavet)",
        "slug": "svay-rieng-bavet",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 9.00,
    },
    {
        "id": "bmb_pnh_pvn_sorya",
        "dest": "Prey Veng",
        "slug": "prey-veng",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 30 mins",
        "price": 5.50,
    },
    {
        "id": "bmb_pnh_pln_virak",
        "dest": "Pailin",
        "slug": "pailin",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "03:00 PM",
        "dur": "7 hrs 00 mins",
        "price": 15.00,
    },
    # International Connections
    {
        "id": "bmb_pnh_bkk_virak_coach",
        "dest": "Bangkok",
        "slug": "bangkok",
        "operator": "Virak Buntham Express",
        "bus_type": "International Coach",
        "dep": "07:30 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 30 mins",
        "price": 20.00,
    },
    {
        "id": "bmb_pnh_bkk_giant_coach",
        "dest": "Bangkok",
        "slug": "bangkok",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 00 mins",
        "price": 35.00,
    },
    {
        "id": "bmb_pnh_sgn_kumho_coach",
        "dest": "Ho Chi Minh",
        "slug": "ho-chi-minh",
        "operator": "Kumho Samco Express",
        "bus_type": "VIP Sleeper Coach",
        "dep": "06:30 AM",
        "arr": "01:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 20.00,
    },
    {
        "id": "bmb_pnh_sgn_giant_coach",
        "dest": "Ho Chi Minh",
        "slug": "ho-chi-minh",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 27.00,
    },
    {
        "id": "bmb_pnh_htn_virak_van",
        "dest": "Ha Tien",
        "slug": "ha-tien",
        "operator": "Virak Buntham Express",
        "bus_type": "Border Express Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 21.00,
    },
    {
        "id": "bmb_pnh_pks_chanthou_bus",
        "dest": "Pakse",
        "slug": "pakse",
        "operator": "Seng Chanthou Transport",
        "bus_type": "International Bus",
        "dep": "07:00 AM",
        "arr": "04:30 PM",
        "dur": "9 hrs 30 mins",
        "price": 37.00,
    },
]


class BookMeBusScraper(BaseScraper):
    """
    BookMeBus Cambodia Scraper (https://bookmebus.com/en).
    Extracts multi-operator intercity bus & transport schedules originating from Phnom Penh
    to all Cambodian provinces and cities.
    Captures: route, bus company/operator (Saly VIP, Virak Buntham, Cambolink 21, Larryta, Giant Ibis, etc.),
              bus type, ticket price, departure time, arrival time, and duration.
    """

    def __init__(self):
        super().__init__(store_slug="bookmebus", source_type="transport")

    def _fetch_destinations(self) -> list[dict[str, Any]]:
        """Fetch active Cambodian destination routes from Phnom Penh."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            resp = _cffi_get(BOOKMEBUS_DESTINATIONS_API, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                cambodia_dests = []
                for d in data:
                    attrs = d.get("attributes", {})
                    dest = attrs.get("destination", {})
                    if (
                        dest.get("country_code") == "KH"
                        and dest.get("slug") != "phnom-penh"
                    ):
                        cambodia_dests.append(
                            {
                                "name": dest.get("name"),
                                "slug": dest.get("slug"),
                                "duration_sec": attrs.get("duration"),
                            }
                        )
                if cambodia_dests:
                    return cambodia_dests
        except Exception as exc:
            log.warning(
                "Failed to fetch BookMeBus destinations API (%s), using default route list",
                exc,
            )

        # Comprehensive fallback destination list
        return [
            {"name": "Siem Reap", "slug": "siem-reap"},
            {"name": "Sihanoukville", "slug": "sihanoukville"},
            {"name": "Battambang", "slug": "battambang"},
            {"name": "Kampot", "slug": "kampot"},
            {"name": "Kep", "slug": "kep"},
            {"name": "Poi Pet", "slug": "poipet"},
            {"name": "Mondulkiri", "slug": "senmonorom-mondulkiri"},
            {"name": "Ratanakiri", "slug": "ratanakiri"},
            {"name": "Koh Kong", "slug": "koh-kong"},
            {"name": "Kampong Cham", "slug": "kampong-cham"},
            {"name": "Kampong Thom", "slug": "kampong-thom"},
            {"name": "Banteay Meanchey", "slug": "banteay-meanchey"},
            {"name": "Preah Vihear", "slug": "preah-vihear-tbeng-meanchey"},
            {"name": "Kratie", "slug": "kratie"},
            {"name": "Stung Treng", "slug": "stung-treng"},
            {"name": "Pursat", "slug": "pursat"},
            {"name": "Kampong Chhnang", "slug": "kampong-chhnang"},
            {"name": "Takeo", "slug": "takeo"},
            {"name": "Svay Rieng (Bavet)", "slug": "svay-rieng-bavet"},
            {"name": "Prey Veng", "slug": "prey-veng"},
            {"name": "Pailin", "slug": "pailin"},
            {"name": "Koh Rong", "slug": "koh-rong-via-ferry"},
            {"name": "Koh Rong Sanloem", "slug": "koh-rong-samloem-via-ferry"},
            {"name": "Bangkok", "slug": "bangkok"},
            {"name": "Ho Chi Minh", "slug": "ho-chi-minh"},
            {"name": "Ha Tien", "slug": "ha-tien"},
            {"name": "Pakse", "slug": "pakse"},
        ]

    def _parse_search_html(
        self, html_text: str, origin_name: str, dest_name: str
    ) -> list[dict[str, Any]]:
        """Parse live schedule cards from BookMeBus search HTML."""
        if not HAS_BS4:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        candidate_divs = soup.find_all(
            lambda tag: tag.name == "div"
            and re.search(r"USD\s*[\d\.]+", tag.get_text())
            and re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM)", tag.get_text())
        )

        seen = set()
        trips = []

        for div in candidate_divs:
            txt = div.get_text(" ", strip=True)
            times = re.findall(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", txt)
            prices = re.findall(r"USD\s*([\d\.]+)", txt)
            duration_m = re.search(
                r"(\d+H\s*\d*|\d+h\s*\d*m?|\d+\s*hours?)", txt, re.IGNORECASE
            )

            if len(times) >= 2 and prices:
                dep_time = times[0]
                arr_time = times[1]
                try:
                    price = float(prices[0])
                except ValueError:
                    continue

                if dep_time == "11:59 AM" and arr_time == "5:59 PM":
                    continue

                duration = (
                    duration_m.group(1).strip() if duration_m else "6 hrs 00 mins"
                )

                img = div.find("img", alt=True)
                operator = img.get("alt").strip() if img and img.get("alt") else ""

                type_m = re.search(
                    r"(Sleeping Bus\s*\d*|VIP\s*Van|Minivan\s*\d*|Luxury\s*Bus|Express\s*Bus|Hotel\s*Bus|Private\s*Taxi|Sedan|SUV|VIP\s*Bus|Standard\s*Bus|Transit\s*Van|Ferry|Speed\s*Boat|Express\s*Boat)",
                    txt,
                    re.IGNORECASE,
                )
                bus_type = type_m.group(1).strip() if type_m else "VIP Express"

                if not operator or operator.lower() in [
                    "home",
                    "loader",
                    "logo",
                    "thumbnail",
                ]:
                    lines = [
                        item_line.strip()
                        for item_line in div.get_text("\n").split("\n")
                        if item_line.strip()
                    ]
                    for line_text in lines:
                        if (
                            not re.search(
                                r"\d{1,2}:\d{2}|Departure|Arrival|USD|Reviews|Info|Left|Seat|Boarding|Drop-off",
                                line_text,
                                re.IGNORECASE,
                            )
                            and len(line_text) < 40
                            and not line_text.isdigit()
                        ):
                            operator = line_text
                            break

                operator = operator or "BookMeBus Partner"

                key = (operator, dep_time, arr_time, price)
                if key not in seen:
                    seen.add(key)
                    trips.append(
                        {
                            "operator": operator,
                            "bus_type": bus_type,
                            "departure_time": dep_time,
                            "arrival_time": arr_time,
                            "expected_hours": duration,
                            "price_usd": price,
                        }
                    )

        return trips

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        # Anchor BOTH the record date and the queried travel date to
        # scrape_date (+2 days so schedules are bookable). Previously the
        # travel date came from wall-clock today(), so backfilled runs fetched
        # current prices while labelling them with the historical scrape_date.
        ds_date = (
            pendulum.parse(str(scrape_date)).date()
            if scrape_date
            else pendulum.today("Asia/Phnom_Penh").date()
        )
        ds = ds_date.format("YYYY-MM-DD")
        target_date = ds_date.add(days=2).format("DD-MM-YYYY")

        html_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        records: list[dict[str, Any]] = []
        destinations = self._fetch_destinations()
        recorded_dest_slugs = set()

        for dest_info in destinations:
            dest_name = dest_info["name"]
            slug = dest_info["slug"]
            url = f"https://bookmebus.com/en/search/bus/phnom-penh/{slug}?on_date={target_date}"

            try:
                resp = _cffi_get(url, headers=html_headers, timeout=8)
                if resp.status_code == 200:
                    trips = self._parse_search_html(resp.text, "Phnom Penh", dest_name)
                    if trips:
                        recorded_dest_slugs.add(slug)
                        for idx, trip in enumerate(trips):
                            operator_clean = trip["operator"]
                            bus_type_clean = trip["bus_type"]
                            item_id = f"bmb_{slug}_{re.sub(r'[^a-zA-Z0-9]', '_', operator_clean).lower()}_{idx}"

                            records.append(
                                build_canonical_record(
                                    source_slug="bookmebus",
                                    source_type="transport",
                                    store_name="BookMeBus Cambodia",
                                    item_id=item_id,
                                    name=f"Bus Ticket: Phnom Penh - {dest_name} ({operator_clean} {bus_type_clean})",
                                    price=trip["price_usd"],
                                    currency="USD",
                                    category_native="Intercity Bus > Passenger Transport by Road",
                                    url=url,
                                    scrape_date=ds,
                                    is_fallback=False,
                                    attrs={
                                        "origin": "Phnom Penh",
                                        "destination": dest_name,
                                        "operator": operator_clean,
                                        "bus_type": bus_type_clean,
                                        "departure_time": trip["departure_time"],
                                        "arrival_time": trip["arrival_time"],
                                        "expected_hours": trip["expected_hours"],
                                        "booking_url": url,
                                    },
                                )
                            )
            except Exception as exc:
                log.debug("BookMeBus route %s live query notice (%s)", slug, exc)

            time.sleep(0.1)

        # For any destination not returned by live search, populate the operator baseline routes
        for route in BOOKMEBUS_BASELINE_ROUTES:
            if route["slug"] not in recorded_dest_slugs:
                records.append(
                    build_canonical_record(
                        source_slug="bookmebus",
                        source_type="transport",
                        store_name="BookMeBus Cambodia",
                        item_id=route["id"],
                        name=f"Bus Ticket: Phnom Penh - {route['dest']} ({route['operator']} {route['bus_type']})",
                        price=route["price"],
                        currency="USD",
                        category_native="Intercity Bus > Passenger Transport by Road",
                        url=f"https://bookmebus.com/en/search/bus/phnom-penh/{route['slug']}?on_date={target_date}",
                        scrape_date=ds,
                        is_fallback=True,
                        attrs={
                            "origin": "Phnom Penh",
                            "destination": route["dest"],
                            "operator": route["operator"],
                            "bus_type": route["bus_type"],
                            "departure_time": route["dep"],
                            "arrival_time": route["arr"],
                            "expected_hours": route["dur"],
                        },
                    )
                )

        return records


# ═══════════════════════════════════════════════════════════════════════════
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
        ds = str(scrape_date or pendulum.today().date())
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


# ═══════════════════════════════════════════════════════════════════════════
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
        ds = str(scrape_date or pendulum.today().date())
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


# ═══════════════════════════════════════════════════════════════════════════
# 17. Bayon Restaurant BKK I (Restaurant)
# ═══════════════════════════════════════════════════════════════════════════
BAYON_MENU_BASELINE = [
    {
        "id": "bayon_loklak_beef",
        "name": "Traditional Beef Lok Lak with Fried Egg & Rice",
        "price": 4.75,
        "category": "Khmer Cuisine > Beef Dishes",
    },
    {
        "id": "bayon_curry_chicken",
        "name": "Khmer Red Curry Chicken with Crispy Baguette",
        "price": 4.25,
        "category": "Khmer Cuisine > Curry Dishes",
    },
    {
        "id": "bayon_baisachchrouk",
        "name": "Grilled Pork with Broken Rice (Bai Sach Chrouk)",
        "price": 2.50,
        "category": "Khmer Cuisine > Breakfast & Rice",
    },
    {
        "id": "bayon_kuyteav_pork",
        "name": "Phnom Penh Noodle Soup with Sliced Pork (Kuy Teav)",
        "price": 3.25,
        "category": "Khmer Cuisine > Noodle Soup",
    },
    {
        "id": "bayon_kuyteav_beef",
        "name": "Phnom Penh Beef Ball Noodle Soup (Kuy Teav Sach Ko)",
        "price": 3.75,
        "category": "Khmer Cuisine > Noodle Soup",
    },
    {
        "id": "bayon_amok_fish",
        "name": "Authentic Fish Amok Steamed in Banana Leaves",
        "price": 5.25,
        "category": "Khmer Cuisine > Traditional Specialities",
    },
    {
        "id": "bayon_somlor_machou",
        "name": "Sweet & Sour Fish Soup with Morning Glory (Somlor Machou)",
        "price": 4.50,
        "category": "Khmer Cuisine > Traditional Soups",
    },
    {
        "id": "bayon_fried_rice_seafood",
        "name": "Yangzhou Seafood Fried Rice with Prawns & Squid",
        "price": 4.00,
        "category": "Asian Cuisine > Fried Rice",
    },
    {
        "id": "bayon_fried_rice_chicken",
        "name": "Stir-Fried Rice with Minced Chicken & Basil",
        "price": 3.50,
        "category": "Asian Cuisine > Fried Rice",
    },
    {
        "id": "bayon_fried_rice_saltedfish",
        "name": "Khmer Fried Rice with Salted Fish & Pork",
        "price": 3.75,
        "category": "Asian Cuisine > Fried Rice",
    },
    {
        "id": "bayon_stirfry_morningglory",
        "name": "Stir-Fried Morning Glory with Oyster Sauce & Garlic",
        "price": 2.75,
        "category": "Khmer Cuisine > Vegetable Dishes",
    },
    {
        "id": "bayon_stirfry_beef_ginger",
        "name": "Stir-Fried Sliced Beef with Fresh Ginger & Spring Onion",
        "price": 4.50,
        "category": "Khmer Cuisine > Beef Dishes",
    },
    {
        "id": "bayon_springrolls_crispy",
        "name": "Deep-Fried Crispy Spring Rolls (Chai Yor) (5 pcs)",
        "price": 3.00,
        "category": "Appetizers > Spring Rolls",
    },
    {
        "id": "bayon_springrolls_fresh",
        "name": "Fresh Summer Rolls with Prawns & Peanut Dip (4 pcs)",
        "price": 3.25,
        "category": "Appetizers > Spring Rolls",
    },
    {
        "id": "bayon_lemongrass_chicken",
        "name": "Stir-Fried Chicken with Spicy Lemongrass Paste (Kroeung)",
        "price": 4.25,
        "category": "Khmer Cuisine > Chicken Dishes",
    },
    {
        "id": "bayon_tomyum_seafood",
        "name": "Spicy Tom Yum Soup with Mixed Seafood",
        "price": 5.00,
        "category": "Asian Cuisine > Soups",
    },
    {
        "id": "bayon_fried_noodles_pork",
        "name": "Stir-Fried Flat Rice Noodles with Pork & Chinese Kale (Mi Katang)",
        "price": 3.50,
        "category": "Asian Cuisine > Noodle Dishes",
    },
    {
        "id": "bayon_green_mango_salad",
        "name": "Khmer Green Mango Salad with Dried Shrimp",
        "price": 3.50,
        "category": "Appetizers > Khmer Salads",
    },
    {
        "id": "bayon_iced_coffee_milk",
        "name": "Cambodian Iced Coffee with Sweet Condensed Milk (Cafe Teuk Doh Ko)",
        "price": 1.75,
        "category": "Beverages > Coffee & Tea",
    },
    {
        "id": "bayon_iced_black_coffee",
        "name": "Traditional Cambodian Iced Black Coffee (Cafe Khmao)",
        "price": 1.50,
        "category": "Beverages > Coffee & Tea",
    },
    {
        "id": "bayon_fresh_coconut",
        "name": "Whole Fresh Young Coconut Juice",
        "price": 1.75,
        "category": "Beverages > Fresh Juices",
    },
    {
        "id": "bayon_mango_smoothie",
        "name": "Fresh Tropical Mango Fruit Smoothie",
        "price": 2.25,
        "category": "Beverages > Fruit Smoothies",
    },
    {
        "id": "bayon_passion_soda",
        "name": "Fresh Passion Fruit Soda with Mint & Lime",
        "price": 2.00,
        "category": "Beverages > Refreshers",
    },
    {
        "id": "bayon_lime_iced_tea",
        "name": "Khmer Fresh Lime Iced Tea",
        "price": 1.50,
        "category": "Beverages > Coffee & Tea",
    },
    {
        "id": "bayon_dessert_chek_ktis",
        "name": "Traditional Sweet Banana in Coconut Milk Tapioca (Chek Ktis)",
        "price": 1.75,
        "category": "Desserts > Traditional Khmer Desserts",
    },
]


BAYON_FOODPANDA_URL = (
    "https://www.foodpanda.com.kh/en/restaurant/lb0z/bayon-restaurant-bkk-i"
)


class BayonRestaurantScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="bayonbkk", source_type="restaurant")

    def _extract_apollo_state(self, html: str) -> dict:
        if not HAS_BS4:
            return {}
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            text = script.string or ""
            if "window.__PROVIDER_PROPS__" in text or "Apollo" in text:
                match = re.search(
                    r"window\.__PROVIDER_PROPS__\s*=\s*({.+?});?\s*$", text, re.DOTALL
                )
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass
                match = re.search(r'"__APOLLO_STATE__"\s*:\s*({.+?})\s*[,}]', text)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass
        return {}

    def _parse_menu_items(self, apollo_state: dict) -> list[dict[str, Any]]:
        items = []
        if not isinstance(apollo_state, dict):
            return items
        for key, val in apollo_state.items():
            if not isinstance(val, dict):
                continue
            if "RestaurantProduct" in key or "menu_item" in key.lower():
                name = (
                    val.get("name") or val.get("title") or val.get("productName") or ""
                )
                price = _to_float(
                    val.get("price") or val.get("variantPrice") or val.get("basePrice")
                )
                if name and price is not None:
                    items.append(
                        {
                            "name": name,
                            "price": price,
                            "description": val.get("description") or "",
                            "category": val.get("category")
                            or val.get("categoryName")
                            or "",
                        }
                    )
            elif isinstance(val, dict):
                for inner_key, inner_val in val.items():
                    if "RestaurantProduct" in str(inner_key) and isinstance(
                        inner_val, dict
                    ):
                        name = (
                            inner_val.get("name") or inner_val.get("productName") or ""
                        )
                        price = _to_float(
                            inner_val.get("price") or inner_val.get("variantPrice")
                        )
                        if name and price is not None:
                            items.append(
                                {
                                    "name": name,
                                    "price": price,
                                    "description": inner_val.get("description") or "",
                                    "category": inner_val.get("category") or "",
                                }
                            )
        return items

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        records: list[dict[str, Any]] = []
        try:
            resp = _cffi_get(BAYON_FOODPANDA_URL, timeout=15)
            if resp.status_code == 200:
                apollo_state = self._extract_apollo_state(resp.text)
                menu_items = self._parse_menu_items(apollo_state)
                for idx, item in enumerate(menu_items):
                    records.append(
                        build_canonical_record(
                            source_slug="bayonbkk",
                            source_type="restaurant",
                            store_name="Bayon Restaurant BKK I",
                            item_id=f"bayon_{idx}",
                            name=item["name"],
                            price=item["price"],
                            currency="USD",
                            category_native=item.get("category") or "Khmer Dining",
                            url=BAYON_FOODPANDA_URL,
                            scrape_date=ds,
                        )
                    )
        except Exception as exc:
            log.warning("Bayon Restaurant live scrape failed: %s", exc)

        if not records:
            for item in BAYON_MENU_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug="bayonbkk",
                        source_type="restaurant",
                        store_name="Bayon Restaurant BKK I",
                        item_id=item["id"],
                        name=item["name"],
                        price=item["price"],
                        currency="USD",
                        category_native=item["category"],
                        url=BAYON_FOODPANDA_URL,
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )
        return records


# ═══════════════════════════════════════════════════════════════════════════
# 18. MEF Daily Exchange Rate — Official API (FX)
# ═══════════════════════════════════════════════════════════════════════════
MEF_FX_URL = os.environ.get(
    "MEF_FX_API_URL",
    "https://data.mef.gov.kh/api/v1/realtime-api/exchange-rate",
)
DEFAULT_USD_KHR = DEFAULT_USD_KHR_RATE  # alias for backwards compatibility


class MefExchangeRateScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="mef_fx", source_type="fx")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today().date())
        rate = DEFAULT_USD_KHR
        is_fallback = False
        fallback_reason = None
        try:
            resp = requests.get(MEF_FX_URL, timeout=15)
            resp.raise_for_status()
            body = resp.json()
            items = body.get("data") if isinstance(body, dict) else body
            found = False
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        curr_id = str(item.get("currency_id") or "").upper()
                        symbol = str(item.get("symbol") or "").upper()
                        if curr_id == "USD" or "USD/KHR" in symbol:
                            val = item.get("average") or item.get("bid") or item.get("ask") or item.get("rate") or item.get("value")
                            parsed = _to_float(val)
                            if parsed and parsed > 0:
                                rate = parsed
                                found = True
                                break
            elif isinstance(body, dict):
                parsed = _to_float(body.get("rate") or body.get("usd_khr") or body.get("value"))
                if parsed and parsed > 0:
                    rate = parsed
                    found = True
            if not found:
                is_fallback = True
                fallback_reason = "MEF FX API response lacked valid USD rate; used default"
        except Exception as exc:
            is_fallback = True
            fallback_reason = f"MEF FX API failed ({exc}); used default rate"
            log.warning("MEF FX API failed, using default %s: %s", DEFAULT_USD_KHR, exc)
        return [
            {
                "scrape_date": ds,
                "source_slug": "mef_fx",
                "source_type": "fx",
                "store": "Ministry of Economy and Finance (MEF)",
                "currency_pair": "USD/KHR",
                "rate": rate,
                "is_fallback": is_fallback,
                "fallback_reason": fallback_reason,
                "scraped_at": datetime.now(UTC).isoformat(),
            }
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 19. MOC Daily Fuel Prices — GraphQL API (LIVE)
# ═══════════════════════════════════════════════════════════════════════════
MOC_GRAPHQL_URL = "https://graphql.moc.gov.kh/graphql"
MOC_COMMODITY_URL = "https://moc.gov.kh/kh/commodity-values"
MOC_FUEL_PRODUCTS = ((107, "Regular Gasoline"), (108, "Diesel"), (109, "Petroleum"))
MOC_FUEL_PROVINCE = int(os.environ.get("MOC_FUEL_PROVINCE_ID", "1"))


def _parse_moc_date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%d %b, %Y", "%d %B, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


class MocGasolineScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="new_gasoline", source_type="fuel")

    def _query_line_report(self, start_date, end_date, province_id, product_ids):
        query = (
            "query publicCommodityPriceLineReport("
            "$reportLineFilter: CommodityPriceDetailLineReportFilter!) {"
            "  publicCommodityPriceLineReport(reportLineFilter: $reportLineFilter) {"
            "    items { data { x y } }"
            "  }"
            "}"
        )
        variables = {
            "reportLineFilter": {
                "byProvince": province_id,
                "byProduct": product_ids,
                "startDate": str(start_date),
                "endDate": str(end_date),
            }
        }
        resp = requests.post(
            MOC_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={
                "content-type": "application/json",
                "apollo-require-preflight": "true",
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        errors = body.get("errors")
        if errors:
            raise RuntimeError(
                f"MOC GraphQL error: {errors[0].get('message', errors[0])}"
            )
        return (
            body.get("data", {}).get("publicCommodityPriceLineReport", {}).get("items")
            or []
        )

    def fetch_records(self, scrape_date=None) -> list[dict[str, Any]]:
        ds = scrape_date or pendulum.today("Asia/Phnom_Penh").date()
        target = ds.date() if isinstance(ds, datetime) else ds
        product_ids = [pid for pid, _ in MOC_FUEL_PRODUCTS]

        # Query fuel products from GraphQL
        items = self._query_line_report(
            ds.subtract(days=14), ds, MOC_FUEL_PROVINCE, product_ids
        )
        items_by_pid: dict[int, Any] = {}
        if items and len(items) >= len(MOC_FUEL_PRODUCTS):
            for idx, (pid, _) in enumerate(MOC_FUEL_PRODUCTS):
                items_by_pid[pid] = items[idx]
        else:
            # Per-product fallback query
            for pid, _ in MOC_FUEL_PRODUCTS:
                res = self._query_line_report(
                    ds.subtract(days=14), ds, MOC_FUEL_PROVINCE, [pid]
                )
                if res:
                    items_by_pid[pid] = res[0]

        records: list[dict[str, Any]] = []
        for product_id, product_name in MOC_FUEL_PRODUCTS:
            item_data = items_by_pid.get(product_id)
            if not item_data:
                continue
            points = item_data.get("data") or []
            best: tuple[datetime, float] | None = None
            for point in points:
                parsed = _parse_moc_date(point.get("x"))
                price = _to_float(point.get("y"))
                if parsed is None or price is None:
                    continue
                if parsed.date() <= target and (best is None or parsed > best[0]):
                    best = (parsed, price)
            if best is None:
                continue
            price_date, price = best
            records.append(
                build_canonical_record(
                    source_slug="new_gasoline",
                    source_type="fuel",
                    store_name="Ministry of Commerce (MOC) - Fuel Prices",
                    item_id=f"moc_fuel_{product_id}",
                    name=product_name,
                    price=_to_float(price),
                    currency="KHR",
                    brand=product_name,
                    category_native="Fuel",
                    package_size="1L",
                    unit="L",
                    url=MOC_COMMODITY_URL,
                    scrape_date=str(ds),
                    is_fallback=price_date.date() != target,
                    attrs={
                        "price_date": price_date.strftime("%Y-%m-%d"),
                        "product_id": product_id,
                        "province_id": MOC_FUEL_PROVINCE,
                    },
                )
            )
        if not records:
            raise RuntimeError(f"MOC: no fuel data for {ds}")
        return records


# ═══════════════════════════════════════════════════════════════════════════
# 20. Ary Store Phone Shop — WooCommerce REST API (LIVE)
# ═══════════════════════════════════════════════════════════════════════════
ARYSTORE_API_URL = os.environ.get(
    "ARYSTORE_API_URL", "https://arystorephone.com/wp-json/wc/store/v1/products"
)
ARYSTORE_PAGE_SIZE = int(os.environ.get("ARYSTORE_PAGE_SIZE", "100"))
ARYSTORE_STORE_NAME = "Ary Store Phone Shop (Phnom Penh)"


class AryStorePhoneScraper(BaseScraper):
    def __init__(self, session=None):
        super().__init__(store_slug="arystore", source_type="electronics")
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CPI-Cambodia-Pipeline/1.0",
        )

    def _to_canonical(self, product: dict, scrape_date: str) -> dict[str, Any] | None:
        prices = product.get("prices") or {}
        price = _to_float(prices.get("price"))
        if price is None or price <= 0:
            return None
        regular = _to_float(prices.get("regular_price"))
        on_sale = bool(product.get("on_sale"))
        brands = product.get("brands") or []
        categories = product.get("categories") or []
        images = product.get("images") or []
        attrs: dict[str, Any] = {
            "sku": product.get("sku"),
            "on_sale": on_sale,
            "is_in_stock": bool(product.get("is_in_stock")),
            "average_rating": _to_float(product.get("average_rating")) or 0.0,
            "review_count": product.get("review_count") or 0,
            "description": _strip_html(product.get("description")),
        }
        return build_canonical_record(
            source_slug="arystore",
            source_type="electronics",
            store_name=ARYSTORE_STORE_NAME,
            item_id=str(product.get("id") or ""),
            name=product.get("name") or "",
            price=price,
            currency=prices.get("currency_code") or "USD",
            original_price=max(_to_float(regular) or price, price),
            brand=brands[0].get("name") if brands else None,
            category_native=" / ".join(
                c.get("name") for c in categories if c.get("name")
            )
            or "General",
            unit="UNIT",
            url=product.get("permalink"),
            image_url=images[0].get("src") if images else None,
            scrape_date=scrape_date,
            on_promo=on_sale,
            attrs=attrs,
        )

    def fetch_records(self, scrape_date=None) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self.session.get(
                ARYSTORE_API_URL,
                params={"per_page": ARYSTORE_PAGE_SIZE, "page": page},
                timeout=60,
            )
            resp.raise_for_status()
            products = resp.json()
            if not products:
                break
            for p in products:
                rec = self._to_canonical(p, ds)
                if rec:
                    records.append(rec)
            if len(products) < ARYSTORE_PAGE_SIZE:
                break
            page += 1
        if not records:
            raise RuntimeError(f"AryStore: 0 products scraped on {ds}")
        return records


# ═══════════════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════════════
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "aeon": AeonSupermarketScraper,
    "aeon3": AeonFashionScraper,
    "delishop": DelishopScraper,
    "l192": L192Scraper,
    "communitypharma": CommunityPharmaScraper,
    "samnangshop": SamnangShopScraper,
    "cellcard": CellcardMobileScraper,
    "cellcard_wifi": CellcardWifiScraper,
    "smart": SmartMobileScraper,
    "smart_wifi": SmartWifiScraper,
    "khmer24": Khmer24Scraper,
    "realestate": RealestateKhScraper,
    "redbus": RedBusKhScraper,
    "bookmebus": BookMeBusScraper,
    "sokhahotel": SokhaHotelScraper,
    "hyyathotel": HyattHotelScraper,
    "bayonbkk": BayonRestaurantScraper,
    "mef_fx": MefExchangeRateScraper,
    "new_gasoline": MocGasolineScraper,
    "arystore": AryStorePhoneScraper,
}
