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

# 21. Ucare Pharmacy Chroy Changva (GrabMart Cambodia)
# ===========================================================================
DEFAULT_UCARE_URL = (
    "https://mart.grab.com/kh/en/merchant/ucare-pharmacy-chroy-changva/10-C7CGV2AFNNEAGJ"
)
UCARE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

UCARE_BASELINE = [
    {
        "id": "KHITE_PARACETAMOL_500MG",
        "name": "Panadol - Paracetamol 500mg 24 Tablets",
        "price": 5000.0,
        "currency": "KHR",
        "brand": "Panadol",
        "category": "OTC Medicine",
    },
    {
        "id": "KHITE_TUMS_ANTACID",
        "name": "TUMS - Calcium Carbonate Usp(1000mg) Chewable Tablets",
        "price": 77700.0,
        "currency": "KHR",
        "brand": "TUMS",
        "category": "OTC Medicine",
    },
    {
        "id": "KHITE_CETAPHIL_CLEANSER",
        "name": "CETAPHIL - Foaming Face Wash for Redness Prone Skin",
        "price": 75900.0,
        "currency": "KHR",
        "brand": "CETAPHIL",
        "category": "Skincare",
    },
    {
        "id": "KHITE_ORAL_JELLY",
        "name": "KAMAGRA - Oral Jelly Watermelon",
        "price": 8000.0,
        "currency": "KHR",
        "brand": "KAMAGRA",
        "category": "Sexual Wellness",
    },
    {
        "id": "KHITE_SWISSE_MULTIVIT",
        "name": "SWISSE - Men's Multivitamin Tablets",
        "price": 102300.0,
        "currency": "KHR",
        "brand": "SWISSE",
        "category": "Vitamins",
    },
]


class GrabUcarePharmacyScraper(BaseScraper):
    """
    Scraper for Ucare Pharmacy Chroy Changva on GrabMart Cambodia.
    Extracts Next.js SSR embedded catalog data (__NEXT_DATA__) with department and item hierarchies.
    """

    def __init__(self, target_url: str | None = None, session: requests.Session | None = None):
        super().__init__(store_slug="grab_ucare", source_type="pharmacy")
        self.target_url = target_url or os.environ.get("UCARE_GRAB_URL", DEFAULT_UCARE_URL)
        self.session = session or requests.Session()
        self.session.headers.update(UCARE_HEADERS)

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        html_text = ""
        for attempt in range(3):
            try:
                resp = _cffi_get(self.target_url, headers=self.session.headers, timeout=30)
                resp.raise_for_status()
                html_text = resp.text
                break
            except Exception as exc:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    log.warning("GrabMart Ucare HTTP GET failed after 3 attempts: %s", exc)

        if html_text:
            try:
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
                    merchant_data = None
                    for qv in queries.values():
                        if isinstance(qv, dict) and "merchant" in qv.get("data", {}):
                            merchant_data = qv["data"]["merchant"]
                            break

                    if merchant_data:
                        store_name = merchant_data.get("name") or "Ucare Pharmacy Chroy Changva"
                        currency = merchant_data.get("currency", {}).get("code", "KHR")
                        departments = merchant_data.get("menu", {}).get("departments", [])

                        seen_ids = set()
                        for dept in departments:
                            dept_name = dept.get("name") or "General"
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
                log.warning("GrabMart Ucare parse failed: %s", parse_err)

        if not records:
            log.warning("GrabMart Ucare live parse returned 0 records; falling back to baseline catalog.")
            for item in UCARE_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type=self.source_type,
                        store_name="Ucare Pharmacy Chroy Changva",
                        item_id=item["id"],
                        name=item["name"],
                        price=item["price"],
                        currency=item.get("currency", "KHR"),
                        brand=item.get("brand"),
                        category_native=item.get("category", "OTC Medicine"),
                        url=self.target_url,
                        scrape_date=ds,
                        is_fallback=True,
                        fallback_reason="baseline_catalog",
                    )
                )

        return records
