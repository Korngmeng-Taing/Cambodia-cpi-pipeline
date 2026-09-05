from __future__ import annotations

import os
import re
import time
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

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    THROTTLE_DELAY,
    _cffi_get,
    _to_float,
    build_canonical_record,
    log,
)


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
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
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
