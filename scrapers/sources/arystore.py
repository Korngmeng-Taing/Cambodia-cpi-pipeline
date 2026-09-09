from __future__ import annotations

import os
import time
from typing import Any

import pendulum
import requests



from scrapers.base import BaseScraper
from scrapers.sources._common import (
    _strip_html,
    _to_float,
    build_canonical_record,
    log,
    parse_woocommerce_prices,
)


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
        price, regular, currency = parse_woocommerce_prices(product.get("prices"))
        if price is None or price <= 0:
            return None
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
            currency=currency,
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
        max_retries = 3
        while True:
            resp = None
            last_err = None
            for attempt in range(max_retries):
                try:
                    resp = self.session.get(
                        ARYSTORE_API_URL,
                        params={"per_page": ARYSTORE_PAGE_SIZE, "page": page},
                        timeout=60,
                    )
                    resp.raise_for_status()
                    break
                except Exception as exc:
                    last_err = exc
                    log.warning("AryStore page %d attempt %d failed: %s", page, attempt + 1, exc)
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            if resp is None:
                log.error("AryStore: all %d retries failed for page %d: %s", max_retries, page, last_err)
                break
            try:
                products = resp.json()
            except Exception:
                log.error("AryStore: invalid JSON on page %d", page)
                break
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
