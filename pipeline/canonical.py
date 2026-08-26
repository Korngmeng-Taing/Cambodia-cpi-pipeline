"""
pipeline/canonical.py
─────────────────────
Canonical Bronze Contract — Schema v1.0.

Every scraper normalizes its output via ``pipeline.canonical.normalize_record()``
so that raw observations strictly conform to the Bronze schema documented in
SCRAPER_METHODOLOGY_GUIDE.md before PostgreSQL bronze and staging writes.

Schema v1.0 contract (extract):
    {
      "scrape_date":  "2026-08-17",
      "source_slug":  "delishop",
      "source_type":  "grocery",
      "store":        "Delishop Cambodia",
      "currency":     "USD",
      "cpi_eligible": true,
      "item_id":      "18492",
      "barcode":      "8850188800123",
      "name":         "Angkor Beer Can 330ml",
      "category_native": "Beers & Ciders",
      "price":        0.85,
      "original_price": 0.95,
      "discount_pct": 10.53,
      "on_promo":     true,
      "promo":        {"type": "discount", "value": 0.10},
      "badges":       ["chilled"],
      "rating":       4.8,
      "image_url":    "...",
      "url":          "...",
      "is_fallback":  false,
      "fallback_reason": null,
      "source":       "scrape",
      "scraped_at":   "2026-08-17T03:00:15Z",
      "attrs":        {"volume_ml": 330},
      "brand":        "Angkor",
      "quantity":     "330ml",
      "package_size": "330ml",
      "unit":         "CAN",
      "is_out_of_stock": false
    }
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

# Price bounds sanity gate (raw price in any currency).
MIN_PRICE = 0.0
MAX_PRICE = 1_000_000_000.0

REQUIRED_FIELDS = (
    "scrape_date",
    "source_slug",
    "source_type",
    "store",
    "currency",
    "item_id",
    "name",
    "price",
)

BOOLEAN_FIELDS = ("cpi_eligible", "is_fallback", "on_promo", "is_out_of_stock")

# Reason recorded on fallback rows so operators can distinguish a live outage
# from a static baseline catalog in Metabase (staging.fallback_alerts trend).
DEFAULT_FALLBACK_REASON = "baseline_catalog"


def _first(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_category(cat: Any) -> str:
    if not cat:
        return "General"
    if isinstance(cat, str):
        c = cat.strip()
        return c if c else "General"
    if isinstance(cat, dict):
        name = (
            cat.get("name")
            or cat.get("title")
            or cat.get("categoryName")
            or cat.get("slug")
        )
        return str(name).strip() if name else "General"
    if isinstance(cat, list):
        parts = []
        for item in cat:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                n = (
                    item.get("name")
                    or item.get("title")
                    or item.get("categoryName")
                    or item.get("slug")
                )
                if n and str(n).strip():
                    parts.append(str(n).strip())
        return " > ".join(parts) if parts else "General"
    return str(cat).strip() or "General"


def _to_bool(val: Any, default: bool = False) -> bool:
    """Robustly converts boolean, int, and string truthy/falsy values to bool."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "1", "yes", "t", "y"):
            return True
        if v in ("false", "0", "no", "f", "n", "none", "null", ""):
            return False
    return bool(val)


def normalize_record(
    raw: dict[str, Any],
    *,
    source_slug: str | None = None,
    source_type: str | None = None,
    store: str | None = None,
    scrape_date: str | None = None,
    currency: str | None = None,
    is_fallback: bool = False,
) -> dict[str, Any]:
    """
    Normalizes a single raw observation to Canonical Bronze Schema v1.0.

    Tolerant of the varied key names produced by the individual source
    scrapers (``name`` / ``title`` / ``item_description`` / ``product_name``,
    ``price`` / ``sale_price``, ``barcode`` / ``barCode`` / ``mpn``, ...).
    """
    if not isinstance(raw, dict):
        raise ValueError(f"normalize_record expects a dict, got {type(raw).__name__}")

    slug = _first(raw.get("source_slug"), raw.get("store_slug"), source_slug)
    if not slug:
        raise ValueError("Canonical record missing required source_slug")

    stype = _first(raw.get("source_type"), source_type, "web")
    store_name = _first(raw.get("store"), raw.get("store_name"), store) or slug
    ds = _first(raw.get("scrape_date"), raw.get("scraped_date"), scrape_date)
    if ds is None:
        ds = datetime.now(UTC).strftime("%Y-%m-%d")

    name = _first(
        raw.get("name"),
        raw.get("title"),
        raw.get("item_description"),
        raw.get("product_name"),
    )
    if not name:
        raise ValueError(f"Canonical record for '{slug}' missing a product name")

    item_id = _first(
        raw.get("item_id"), raw.get("product_id"), raw.get("sku"), raw.get("id")
    )
    if item_id is None:
        item_id = f"{slug}_{hashlib.sha1(str(name).encode('utf-8')).hexdigest()[:12]}"

    raw_curr = _first(raw.get("currency"), currency)
    curr = str(raw_curr).strip().upper() if raw_curr else None

    # Handle price_khr explicit fields or price/sale_price
    price = _as_float(
        _first(raw.get("price"), raw.get("sale_price"), raw.get("price_khr"))
    )
    if price is None or price <= 0:
        raise ValueError(
            f"Canonical record for '{slug}' ('{name}') missing valid positive price: {price}"
        )
    if price > MAX_PRICE:
        raise ValueError(f"Price bound violation for '{slug}' ('{name}'): {price}")

    if curr is None:
        # Default currency inference
        curr = "KHR" if (raw.get("price_khr") is not None or price > 2000.0) else "USD"

    orig_price = _as_float(
        _first(
            raw.get("original_price"),
            raw.get("original"),
            raw.get("msrp"),
            raw.get("compare_at_price"),
        )
    )
    if orig_price is None or orig_price <= 0:
        orig_price = price
    orig_price = max(orig_price, price)

    on_promo_raw = raw.get("on_promo")
    if on_promo_raw is None:
        on_promo = orig_price > price
    else:
        on_promo = _to_bool(on_promo_raw)

    discount_pct = (
        round(((orig_price - price) / orig_price) * 100.0, 2)
        if orig_price > 0 and on_promo
        else 0.0
    )
    promo = (
        {"type": "discount", "value": round(orig_price - price, 2)}
        if on_promo
        else None
    )

    barcode = _first(
        raw.get("barcode"), raw.get("barCode"), raw.get("mpn"), raw.get("barcode_ean")
    )
    brand = _first(raw.get("brand"), raw.get("brand_name"))
    category_native = _first(
        raw.get("category_native"), raw.get("category"), raw.get("native_category")
    )
    package_size = _first(
        raw.get("package_size"),
        raw.get("quantity"),
        raw.get("size"),
        raw.get("pack_size"),
    )
    quantity = _first(raw.get("quantity"), package_size)
    unit = _first(raw.get("unit"), raw.get("unit_size"))
    url = _first(raw.get("url"), raw.get("source_url"), raw.get("link"))
    image_url = _first(
        raw.get("image_url"), raw.get("image"), raw.get("picture"), raw.get("img")
    )
    badges = raw.get("badges") or []
    if not isinstance(badges, list):
        badges = [badges]
    rating = _as_float(raw.get("rating")) or 0.0
    attrs = raw.get("attrs") if isinstance(raw.get("attrs"), dict) else {}

    is_fallback = _to_bool(_first(raw.get("is_fallback"), is_fallback))
    fallback_reason = raw.get("fallback_reason")
    if not is_fallback:
        fallback_reason = None
    elif fallback_reason is None or not str(fallback_reason).strip():
        fallback_reason = DEFAULT_FALLBACK_REASON

    cpi_eligible = _to_bool(_first(raw.get("cpi_eligible"), True), default=True)
    # Circuit breaker: guard against 1000x scaling glitch or extreme price typos in retail goods
    if curr == "KHR" and price > 50_000_000.0 and stype not in ("housing", "hotel"):
        cpi_eligible = False
    elif curr == "USD" and price > 15_000.0 and stype not in ("housing", "hotel"):
        cpi_eligible = False

    return {
        "scrape_date": str(ds),
        "source_slug": str(slug),
        "source_type": str(stype),
        "store": str(store_name),
        "currency": str(curr),
        "cpi_eligible": cpi_eligible,
        "item_id": str(item_id),
        "barcode": str(barcode) if barcode is not None else None,
        "name": str(name),
        "category_native": _normalize_category(category_native),
        "price": price,
        "original_price": orig_price,
        "discount_pct": discount_pct,
        "on_promo": on_promo,
        "promo": promo,
        "badges": list(badges),
        "rating": rating,
        "image_url": str(image_url) if image_url else None,
        "url": str(url) if url else None,
        "is_fallback": is_fallback,
        "fallback_reason": str(fallback_reason) if fallback_reason else None,
        "source": str(raw.get("source") or "scrape"),
        "scraped_at": str(raw.get("scraped_at") or datetime.now(UTC).isoformat()),
        "attrs": attrs,
        "brand": str(brand) if brand else None,
        "quantity": str(quantity) if quantity else None,
        "package_size": str(package_size) if package_size else None,
        "unit": str(unit) if unit else "UNIT",
        "is_out_of_stock": bool(_first(raw.get("is_out_of_stock"), False)),
    }


def normalize_records(
    records: list[dict[str, Any]] | dict[str, Any],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Normalizes a list (or single) of raw observations to Schema v1.0.
    """
    if isinstance(records, dict):
        records = [records]
    return [normalize_record(r, **kwargs) for r in records]


def validate_record(record: dict[str, Any]) -> list[str]:
    """
    Validates a canonical record against Schema v1.0 constraints.

    Returns a list of human-readable violation strings (empty = valid).
    """
    issues: list[str] = []
    for field in REQUIRED_FIELDS:
        if record.get(field) in (None, ""):
            issues.append(f"missing required field '{field}'")

    price = _as_float(record.get("price"))
    if price is not None and not (MIN_PRICE <= price <= MAX_PRICE):
        issues.append(
            f"price {price} outside allowed bounds [{MIN_PRICE}, {MAX_PRICE}]"
        )

    orig = _as_float(record.get("original_price"))
    if price is not None and orig is not None and orig < price:
        issues.append("original_price must be >= price")

    discount = _as_float(record.get("discount_pct"))
    if discount is not None and not (0.0 <= discount <= 100.0):
        issues.append(f"discount_pct {discount} outside [0, 100]")

    if record.get("on_promo") is True and not record.get("promo"):
        issues.append("on_promo=True requires a promo payload")
    return issues


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Validates a batch of canonical records and returns a summary dict.
    """
    total = len(records)
    errors: list[str] = []
    valid_count = 0
    for rec in records:
        issues = validate_record(rec)
        if issues:
            errors.extend(issues)
        else:
            valid_count += 1
    return {"total": total, "valid_count": valid_count, "error_count": len(errors), "errors": errors}
