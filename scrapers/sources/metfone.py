from __future__ import annotations

import json
from typing import Any

import pendulum

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    _cffi_get,
    _cffi_post,
    _to_float,
    build_canonical_record,
    log,
)

# ═══════════════════════════════════════════════════════════════════════════
# Metfone Cambodia — Mobile Bundles & Home Internet / FTTH (Telecom 08.3.0)
# ═══════════════════════════════════════════════════════════════════════════
METFONE_MOBILE_URL = "https://metfone.com.kh/en/mobile?tab=0"
METFONE_HOME_URL = "https://metfone.com.kh/en/home-package"

# Baseline tariff matrix verified against Metfone Cambodia live website
METFONE_MOBILE_PLANS = [
    {
        "id": "met_kado_1_plus",
        "name": "Metfone KADO 1 Plus 8GB (7 Days)",
        "price": 1.00,
        "type": "Mobile Prepaid > Weekly Bundle",
        "data": "8GB",
    },
    {
        "id": "met_kado_1_5_plus",
        "name": "Metfone KADO 1.5 Plus 15GB (7 Days)",
        "price": 1.50,
        "type": "Mobile Prepaid > Weekly Bundle",
        "data": "15GB",
    },
    {
        "id": "met_kado_6_plus",
        "name": "Metfone KADO 6 Plus 60GB (30 Days)",
        "price": 6.00,
        "type": "Mobile Prepaid > Monthly Bundle",
        "data": "60GB",
    },
    {
        "id": "met_kado_10_plus",
        "name": "Metfone KADO 10 Plus 100GB (30 Days)",
        "price": 10.00,
        "type": "Mobile Prepaid > Monthly Bundle",
        "data": "100GB",
    },
    {
        "id": "met_kado_1",
        "name": "Metfone KADO 1 5GB (7 Days)",
        "price": 1.00,
        "type": "Mobile Prepaid > Weekly Bundle",
        "data": "5GB",
    },
    {
        "id": "met_kado_1_5_social",
        "name": "Metfone KADO 1.5 Social 10GB (7 Days)",
        "price": 1.50,
        "type": "Mobile Prepaid > Social Pack",
        "data": "10GB",
    },
    {
        "id": "met_kado_1_5_entertain",
        "name": "Metfone KADO 1.5 Entertain 10GB (7 Days)",
        "price": 1.50,
        "type": "Mobile Prepaid > Entertainment Pack",
        "data": "10GB",
    },
    {
        "id": "met_kado_4",
        "name": "Metfone KADO 4 25GB (30 Days)",
        "price": 4.00,
        "type": "Mobile Prepaid > Monthly Bundle",
        "data": "25GB",
    },
    {
        "id": "met_kado_seksa",
        "name": "Metfone KADO Seksa 40GB (30 Days)",
        "price": 5.00,
        "type": "Mobile Prepaid > Education Pack",
        "data": "40GB",
    },
    {
        "id": "met_kado_6",
        "name": "Metfone KADO 6 50GB (30 Days)",
        "price": 6.00,
        "type": "Mobile Prepaid > Monthly Bundle",
        "data": "50GB",
    },
]

METFONE_HOME_PLANS = [
    {
        "id": "met_home_basic_50m",
        "name": "Metfone Home Internet Fiber 50 Mbps",
        "price": 15.00,
        "type": "Broadband Internet > Home Fiber",
        "speed": "50 Mbps",
    },
    {
        "id": "met_home_plus1_100m",
        "name": "Metfone Home Plus 1 Fiber 100 Mbps",
        "price": 18.00,
        "type": "Broadband Internet > Home Fiber",
        "speed": "100 Mbps",
    },
    {
        "id": "met_home_plus2_150m",
        "name": "Metfone Home Plus 2 Fiber 150 Mbps",
        "price": 25.00,
        "type": "Broadband Internet > Home Fiber",
        "speed": "150 Mbps",
    },
    {
        "id": "met_home_plus3_200m",
        "name": "Metfone Home Plus 3 Fiber 200 Mbps",
        "price": 35.00,
        "type": "Broadband Internet > Home Fiber",
        "speed": "200 Mbps",
    },
]


class MetfoneScraper(BaseScraper):
    """Metfone Cambodia Scraper covering KADO Prepaid Mobile Bundles and Home Fiber Internet."""

    def __init__(self, store_slug: str = "metfone"):
        super().__init__(store_slug=store_slug, source_type="telecom")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        # 1. Live scrape via Metfone Next.js Proxy API (REST JSON)
        try:
            api_url = "https://metfone.com.kh/api/proxy/packages/config-des-packages"
            payload = {
                "wsCode": "getConfigDesPackages",
                "wsRequest": {
                    "servicePackagesCode": "MOBILE_CODE",
                    "type": 2,
                    "language": "en",
                    "role": "",
                },
            }
            resp = _cffi_post(api_url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for root in data.get("wsResponse") or []:
                    for child in root.get("listChildConfigDes") or []:
                        for pkg in child.get("listPackage") or []:
                            name = pkg.get("name")
                            price = _to_float(pkg.get("price"))
                            if name and price:
                                pkg_id = str(pkg.get("id") or name.lower().replace(" ", "_"))
                                data_size = f"{pkg.get('numberPackages', '')} {pkg.get('unitPackage', '')}".strip() or None
                                validity = f"{pkg.get('numberDateApplicable', '')}{pkg.get('unitDateApplicable', '')}".strip()
                                records.append(
                                    build_canonical_record(
                                        source_slug=self.store_slug,
                                        source_type="telecom",
                                        store_name="Metfone Cambodia Mobile",
                                        item_id=f"met_live_{pkg_id}",
                                        name=f"Metfone {name} ({validity})" if validity else f"Metfone {name}",
                                        price=price,
                                        currency="USD",
                                        category_native="Mobile Prepaid > Weekly/Monthly Bundle",
                                        package_size=data_size,
                                        url=METFONE_MOBILE_URL,
                                        scrape_date=ds,
                                        attrs={
                                            "days_applicable": pkg.get("numberDateApplicable"),
                                            "dial_code": pkg.get("toSubscribeDial") or pkg.get("guideRegister"),
                                        },
                                    )
                                )
        except Exception as exc:
            log.warning("Metfone Mobile live proxy API error: %s", exc)

        # Supplement live records with any baseline mobile plans not covered by live scrape
        live_names = {r["name"].lower() for r in records}
        for plan in METFONE_MOBILE_PLANS:
            plan_name = plan["name"]
            # Check if plan is already represented by live scrape
            p_core = plan_name.lower().replace("metfone", "").strip()
            if not any(p_core in ln or ln in p_core for ln in live_names):
                records.append(
                    build_canonical_record(
                        source_slug=self.store_slug,
                        source_type="telecom",
                        store_name="Metfone Cambodia Mobile",
                        item_id=plan["id"],
                        name=plan["name"],
                        price=plan["price"],
                        currency="USD",
                        category_native=plan["type"],
                        package_size=plan["data"],
                        url=METFONE_MOBILE_URL,
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )

        # 2. Add Home Internet / Fiber plans
        for plan in METFONE_HOME_PLANS:
            records.append(
                build_canonical_record(
                    source_slug=self.store_slug,
                    source_type="telecom",
                    store_name="Metfone Home Internet",
                    item_id=plan["id"],
                    name=plan["name"],
                    price=plan["price"],
                    currency="USD",
                    category_native=plan["type"],
                    package_size=plan["speed"],
                    url=METFONE_HOME_URL,
                    scrape_date=ds,
                    is_fallback=True,
                )
            )

        return records
