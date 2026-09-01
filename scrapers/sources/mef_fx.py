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


# 18. MEF Daily Exchange Rate — Official API (FX)
# ═══════════════════════════════════════════════════════════════════════════
MEF_FX_URL = os.environ.get(
    "MEF_FX_API_URL",
    "https://data.mef.gov.kh/api/v1/realtime-api/exchange-rate",
)

class MefExchangeRateScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="mef_fx", source_type="fx")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        rate = DEFAULT_USD_KHR_RATE
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
            log.warning("MEF FX API failed, using default %s: %s", DEFAULT_USD_KHR_RATE, exc)
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
