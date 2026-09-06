from __future__ import annotations

import os
import time
from typing import Any

import pendulum

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

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    THROTTLE_DELAY,
    _cffi_get,
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


def _extract_aeon_category_targets(filters: dict) -> list[tuple[int, str]]:
    """Extracts level-2 (or level-1 if no children) category targets to query via categoryIds.
    This guarantees that every returned product is stamped with its true specific category
    (e.g. 'Grocery > Beer', 'Health & Hygiene > Cleaning liquid', 'Household > Kitchen')
    rather than a blanket fallback like 'Grocery'.
    """
    targets: list[tuple[int, str]] = []
    roots = filters.get("categories") if isinstance(filters, dict) else []
    for root in (roots or []):
        if not isinstance(root, dict) or not root.get("id"):
            continue
        r_id = root["id"]
        r_name = root.get("name") or ""
        # Skip purely generic marketing/event banners if specific subcategories exist
        if r_name.lower() in ("special offer up to 50% off", "event"):
            continue
        children = root.get("children") or []
        if children:
            for child in children:
                if isinstance(child, dict) and child.get("id"):
                    c_id = child["id"]
                    c_name = child.get("name") or ""
                    targets.append((c_id, f"{r_name} > {c_name}"))
        else:
            targets.append((r_id, r_name))
    return targets


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
        seen_ids: set[str] = set()

        # Step 1: Discover category hierarchy from initial probe
        targets: list[tuple[int, str]] = []
        cat_map: dict[int, str] = {}
        for attempt in range(4):
            try:
                resp = _cffi_get(
                    AEON1_API,
                    params={"page": 1, "limit": 10},
                    headers=AEON_HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                probe_body = resp.json()
                if isinstance(probe_body.get("filters"), dict):
                    cat_map = _build_aeon_category_map(probe_body["filters"])
                    targets = _extract_aeon_category_targets(probe_body["filters"])
                break
            except Exception as exc:
                time.sleep(1.5 * (attempt + 1))

        # Fallback to single stream if category filter tree was not discovered
        if not targets:
            targets = [(None, "Grocery")]

        for cat_id, cat_path in targets:
            page = 1
            total_pages = 999
            consecutive_errors = 0
            while page <= total_pages:
                if AEON_MAX_PAGES > 0 and page > AEON_MAX_PAGES:
                    break
                params = {"page": page, "limit": AEON1_PAGE_SIZE}
                if cat_id:
                    params["categoryIds"] = cat_id

                body = None
                for attempt in range(5):
                    try:
                        resp = _cffi_get(
                            AEON1_API,
                            params=params,
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
                            log.warning("AEON1 cat %s page %d error: %s", cat_path, page, exc)

                if not body:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        break
                    page += 1
                    time.sleep(1.5)
                    continue

                consecutive_errors = 0
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
                    p_id = str(p.get("id", ""))
                    if not p_id or p_id in seen_ids:
                        continue
                    seen_ids.add(p_id)

                    price = _to_float(p.get("salePrice") or p.get("price"))
                    if price is None:
                        continue
                    orig = _to_float(
                        p.get("fullPriceBeforeDiscount") or p.get("originalPrice")
                    )
                    on_sale = bool(p.get("discount") or (orig and orig > price))

                    # Use verified category path from the target query, or category map
                    item_cat_id = p.get("categoryId") or cat_id
                    item_cat_name = cat_map.get(item_cat_id) or cat_path or "Grocery"

                    records.append(
                        build_canonical_record(
                            source_slug="aeon",
                            source_type="grocery",
                            store_name="AEON 1 Phnom Penh",
                            item_id=p_id,
                            name=p.get("name") or p.get("title") or "",
                            price=price,
                            currency="KHR",
                            original_price=orig,
                            barcode=p.get("barcode"),
                            brand=p.get("brand"),
                            category_native=item_cat_name,
                            package_size=p.get("size") or p.get("quantity"),
                            url=p.get("url")
                            or f"https://aeononlineshopping.com/product/{p_id}",
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
        seen_ids: set[str] = set()

        # Step 1: Discover category hierarchy from initial probe
        targets: list[tuple[int, str]] = []
        cat_map: dict[int, str] = {}
        for attempt in range(4):
            try:
                resp = _cffi_get(
                    AEON3_API,
                    params={"page": 1, "limit": 10},
                    headers=AEON_HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                probe_body = resp.json()
                if isinstance(probe_body.get("filters"), dict):
                    cat_map = _build_aeon_category_map(probe_body["filters"])
                    targets = _extract_aeon_category_targets(probe_body["filters"])
                break
            except Exception as exc:
                time.sleep(1.5 * (attempt + 1))

        if not targets:
            targets = [(None, "Fashion & Beauty")]

        for cat_id, cat_path in targets:
            page = 1
            total_pages = 999
            consecutive_errors = 0
            while page <= total_pages:
                if AEON_MAX_PAGES > 0 and page > AEON_MAX_PAGES:
                    break
                params = {"page": page, "limit": AEON3_PAGE_SIZE}
                if cat_id:
                    params["categoryIds"] = cat_id

                body = None
                for attempt in range(5):
                    try:
                        resp = _cffi_get(
                            AEON3_API,
                            params=params,
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
                            log.warning("AEON3 cat %s page %d error: %s", cat_path, page, exc)

                if not body:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        break
                    page += 1
                    time.sleep(1.5)
                    continue

                consecutive_errors = 0
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
                    p_id = str(p.get("id", ""))
                    if not p_id or p_id in seen_ids:
                        continue
                    seen_ids.add(p_id)

                    price = _to_float(p.get("salePrice") or p.get("price"))
                    if price is None:
                        continue
                    orig = _to_float(
                        p.get("fullPriceBeforeDiscount") or p.get("originalPrice")
                    )
                    on_sale = bool(p.get("discount") or (orig and orig > price))

                    item_cat_id = p.get("categoryId") or cat_id
                    item_cat_name = cat_map.get(item_cat_id) or cat_path or "Fashion & Beauty"

                    records.append(
                        build_canonical_record(
                            source_slug="aeon3",
                            source_type="fashion",
                            store_name="AEON 3 Mean Chey",
                            item_id=p_id,
                            name=p.get("name") or p.get("title") or "",
                            price=price,
                            currency="KHR",
                            original_price=orig,
                            barcode=p.get("barcode"),
                            brand=p.get("brand"),
                            category_native=item_cat_name,
                            url=f"https://aeononlineshopping.com/product/{p_id}",
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
