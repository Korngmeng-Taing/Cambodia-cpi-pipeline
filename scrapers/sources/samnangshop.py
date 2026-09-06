from __future__ import annotations

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
    _strip_html,
    _to_float,
    build_canonical_record,
    log,
)


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
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        page = 1
        max_pages = 5
        while page <= max_pages:
            url = f"{KHMERSAMNANG_API}?per_page={KHMERSAMNANG_PAGE_SIZE}&page={page}"
            page_success = False
            for attempt in range(1, 4):
                try:
                    resp = _cffi_get(url, timeout=35)
                    if resp.status_code in (400, 404):
                        page_success = True
                        break
                    resp.raise_for_status()
                    products = resp.json()
                    if not products or not isinstance(products, list):
                        page_success = True
                        break
                    for p in products:
                        rec = self._to_canonical(p, ds)
                        if rec:
                            records.append(rec)
                    page_success = True
                    if len(products) < KHMERSAMNANG_PAGE_SIZE:
                        max_pages = 0
                    break
                except Exception as exc:
                    if attempt < 3:
                        log.warning(
                            "SamnangShop page %d attempt %d failed (%s), retrying in %ds...",
                            page,
                            attempt,
                            exc,
                            attempt * 2,
                        )
                        time.sleep(attempt * 2)
                    else:
                        log.warning(
                            "SamnangShop page %d failed after 3 attempts (%s), stopping pagination",
                            page,
                            exc,
                        )
            if not page_success:
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
