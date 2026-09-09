from __future__ import annotations

import logging
import os
import re
import sys
import threading
from typing import Any

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

log = logging.getLogger(__name__)

THROTTLE_DELAY = float(os.environ.get("SCRAPER_THROTTLE_DELAY", "0.5"))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "")
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


_THREAD_LOCAL = threading.local()


def get_cffi_session():
    """Returns a thread-local persistent Session for connection pooling & TLS reuse."""
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        if HAS_CURL_CFFI:
            session = cffi_requests.Session(impersonate="chrome")
        else:
            session = requests.Session()
        _THREAD_LOCAL.session = session
    return session


def _default_cffi_get(url: str, **kwargs: Any) -> requests.Response:
    """GET via persistent curl_cffi session with Chrome TLS impersonation, falls back to requests."""
    timeout = kwargs.pop("timeout", 30)
    session = get_cffi_session()
    try:
        return session.get(url, timeout=timeout, **kwargs)
    except Exception:
        # Fallback to fresh one-off request if pooled session encountered an issue
        if HAS_CURL_CFFI:
            return cffi_requests.get(url, impersonate="chrome", timeout=timeout, **kwargs)
        return requests.get(url, timeout=timeout, **kwargs)


def _default_cffi_post(url: str, **kwargs: Any) -> requests.Response:
    """POST via persistent curl_cffi session with Chrome TLS impersonation, falls back to requests."""
    timeout = kwargs.pop("timeout", 30)
    session = get_cffi_session()
    try:
        return session.post(url, timeout=timeout, **kwargs)
    except Exception:
        # Fallback to fresh one-off request if pooled session encountered an issue
        if HAS_CURL_CFFI:
            return cffi_requests.post(url, impersonate="chrome", timeout=timeout, **kwargs)
        return requests.post(url, timeout=timeout, **kwargs)


def _cffi_get(url: str, **kwargs: Any) -> requests.Response:
    mod = sys.modules.get("scrapers.sources")
    if mod is not None:
        fn = getattr(mod, "_cffi_get", None)
        if fn is not None and fn is not _cffi_get and fn is not _default_cffi_get:
            return fn(url, **kwargs)
    return _default_cffi_get(url, **kwargs)


def _cffi_post(url: str, **kwargs: Any) -> requests.Response:
    mod = sys.modules.get("scrapers.sources")
    if mod is not None:
        fn = getattr(mod, "_cffi_post", None)
        if fn is not None and fn is not _cffi_post and fn is not _default_cffi_post:
            return fn(url, **kwargs)
    return _default_cffi_post(url, **kwargs)


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
    fallback_reason: str | None = None,
    attrs: dict[str, Any] | None = None,
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


def parse_woocommerce_prices(
    prices: dict[str, Any] | None,
) -> tuple[float | None, float | None, str]:
    """
    Parses WooCommerce REST API prices object handling currency_minor_unit scaling.
    Returns: (price, regular_price, currency_code)
    """
    if not prices:
        return None, None, "USD"
    minor_unit = int(prices.get("currency_minor_unit", 0) or 0)
    scale = 10**minor_unit if minor_unit > 0 else 1

    raw_price = _to_float(prices.get("price"))
    price = raw_price / scale if raw_price is not None else None

    raw_reg = _to_float(prices.get("regular_price"))
    reg_price = raw_reg / scale if raw_reg is not None else None

    currency = str(prices.get("currency_code") or "USD").upper()
    return price, reg_price, currency

