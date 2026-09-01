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


MOC_FUEL_BASELINE = [
    (107, "Regular Gasoline", 5000.0),
    (108, "Diesel", 4050.0),
    (109, "Petroleum", 3950.0),
]


class MocGasolineScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="new_gasoline", source_type="fuel")

    def _query_line_report(self, start_date, end_date, province_id, product_ids, _retries=3):
        # H5 FIX: Use explicit YYYY-MM-DD format to avoid ISO timestamp
        # when pendulum.Date.subtract() returns a DateTime.
        start_str = start_date.format("YYYY-MM-DD") if hasattr(start_date, "format") else str(start_date)
        end_str = end_date.format("YYYY-MM-DD") if hasattr(end_date, "format") else str(end_date)
        
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
                "startDate": start_str,
                "endDate": end_str,
            }
        }
        last_err = None
        for attempt in range(_retries):
            try:
                resp = _cffi_post(
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
            except Exception as exc:
                last_err = exc
                if attempt < _retries - 1:
                    time.sleep(2 ** (attempt + 1))
        log.warning("MOC: all %d retries failed for products %s: %s", _retries, product_ids, last_err)
        return []

    def fetch_records(self, scrape_date=None) -> list[dict[str, Any]]:
        raw = scrape_date or pendulum.today("Asia/Phnom_Penh").date()
        # Ensure ds is a pendulum.Date so .subtract() works
        if isinstance(raw, datetime):
            ds = pendulum.instance(raw).date()
        elif isinstance(raw, pendulum.Date):
            ds = raw
        else:
            ds = pendulum.parse(str(raw)).date()
        target = ds
        product_ids = [pid for pid, _ in MOC_FUEL_PRODUCTS]

        # Query all fuel products in a single batch call.
        # The MOC GraphQL API returns items in the same order as the byProduct input array,
        # so positional mapping (items[idx] ↔ product_ids[idx]) is safe.
        items = self._query_line_report(
            ds.subtract(days=14), ds, MOC_FUEL_PROVINCE, product_ids
        )
        items_by_pid: dict[int, Any] = {}
        if items and len(items) >= len(MOC_FUEL_PRODUCTS):
            for idx, (pid, _) in enumerate(MOC_FUEL_PRODUCTS):
                items_by_pid[pid] = items[idx]
        else:
            # Fallback: query per-product if batch returned incomplete results
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
            log.warning("MOC: live API returned 0 records for %s, using baseline fallback", ds)
            for product_id, product_name, baseline_price in MOC_FUEL_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug="new_gasoline",
                        source_type="fuel",
                        store_name="Ministry of Commerce (MOC) - Fuel Prices",
                        item_id=f"moc_fuel_{product_id}",
                        name=product_name,
                        price=baseline_price,
                        currency="KHR",
                        brand=product_name,
                        category_native="Fuel",
                        package_size="1L",
                        unit="L",
                        url=MOC_COMMODITY_URL,
                        scrape_date=str(ds),
                        is_fallback=True,
                        fallback_reason="moc_api_unreachable",
                    )
                )
        return records
