"""
tests/test_sources.py
────────────────────
Unit tests for all 20 CPI source scrapers + MEF FX rate fetcher.
All live HTTP calls are mocked — tests never hit real endpoints.
"""

import json

import pendulum
import pytest
import requests

from scrapers.sources import SCRAPER_REGISTRY, build_canonical_record


class _FakeResponse:
    """Minimal requests.Response stand-in for mocked HTTP calls."""

    def __init__(self, payload, status_code=200, text=None):
        self._payload = payload
        self.status_code = status_code
        self.text = (
            text or json.dumps(payload)
            if isinstance(payload, (dict, list))
            else (text or "")
        )
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


def _arystore_page(page: int) -> list[dict]:
    """Canned Ary Store WooCommerce Store API responses (2 pages)."""
    if page >= 2:
        return []
    return [
        {
            "id": 1001,
            "name": "iPhone 15 Pro 128GB",
            "slug": "iphone-15-pro-128gb",
            "type": "simple",
            "permalink": "https://arystorephone.com/shop/iphone-15-pro-128gb/",
            "sku": "IP15-128",
            "on_sale": True,
            "prices": {
                "price": "999",
                "regular_price": "1099",
                "sale_price": "999",
                "price_range": None,
                "currency_code": "USD",
            },
            "description": "<p>Flagship smartphone with titanium body.</p>",
            "short_description": "<strong>Apple A17 Pro</strong>",
            "categories": [{"id": 10, "name": "Smartphones"}],
            "tags": [{"id": 1, "name": "apple"}],
            "brands": [{"id": 5, "name": "Apple"}],
            "images": [
                {"src": "https://arystorephone.com/wp-content/uploads/iphone.jpg"}
            ],
            "average_rating": "4.8",
            "review_count": 12,
            "is_in_stock": True,
            "stock_availability": {"text": "In stock", "class": "in-stock"},
            "formatted_weight": "187 g",
        },
        {
            "id": 1002,
            "name": "USB-C Fast Charger 20W",
            "slug": "usb-c-fast-charger-20w",
            "type": "simple",
            "permalink": "https://arystorephone.com/shop/usb-c-fast-charger-20w/",
            "sku": "",
            "on_sale": False,
            "prices": {
                "price": "25",
                "regular_price": "25",
                "sale_price": "25",
                "price_range": None,
                "currency_code": "USD",
            },
            "description": "",
            "short_description": "",
            "categories": [{"id": 47, "name": "Accessories"}],
            "tags": [],
            "brands": [],
            "images": [],
            "average_rating": "0",
            "review_count": 0,
            "is_in_stock": True,
            "stock_availability": {"text": "In stock", "class": "in-stock"},
            "formatted_weight": "N/A",
        },
    ]


# ── Canned data per source ─────────────────────────────────────────────────

_CANNED = {
    "aeon": {
        "products": {
            "data": [
                {
                    "id": "aeon_001",
                    "title": "Jasmine Rice 5kg",
                    "salePrice": 17200,
                    "originalPrice": 18000,
                    "barcode": "8850011001",
                    "brand": "Angkor Harvest",
                    "categoryName": "Rice & Grains",
                    "size": "5kg",
                    "images": ["https://aeon.com/rice.jpg"],
                },
                {
                    "id": "aeon_002",
                    "title": "Fresh Milk 1L",
                    "salePrice": 8500,
                    "originalPrice": None,
                    "barcode": "8850011002",
                    "brand": "Cowhead",
                    "categoryName": "Dairy",
                    "size": "1L",
                    "images": [],
                },
                {
                    "id": "aeon_003",
                    "title": "Eggs Tray 10s",
                    "salePrice": 7300,
                    "originalPrice": None,
                    "barcode": "8850011003",
                    "brand": "CP Fresh",
                    "categoryName": "Fresh Produce",
                    "size": "10pcs",
                    "images": [],
                },
            ],
            "lastPage": 1,
        }
    },
    "aeon3": {
        "products": {
            "data": [
                {
                    "id": "aeon3_001",
                    "title": "Men Cotton T-Shirt",
                    "salePrice": 34300,
                    "originalPrice": 38000,
                    "brand": "Giordano",
                    "categoryName": "Men Clothing",
                    "images": ["https://aeon.com/shirt.jpg"],
                },
                {
                    "id": "aeon3_002",
                    "title": "Women Running Shoes",
                    "salePrice": 117000,
                    "originalPrice": None,
                    "brand": "Bata",
                    "categoryName": "Footwear",
                    "images": [],
                },
            ],
            "lastPage": 1,
        }
    },
    "delishop": {
        "data": [
            {
                "id": "deli_101",
                "name": "Angkor Beer Can 330ml",
                "price": 0.85,
                "original_price": 0.95,
                "barCode": "8850188800123",
                "brand": "Angkor",
                "categoryName": "Beers & Ciders",
                "package_size": "330ml",
                "image": "https://delishop.asia/beer.jpg",
            },
            {
                "id": "deli_102",
                "name": "Avocado Hass Fresh 500g",
                "price": 2.90,
                "original_price": None,
                "barCode": "8850188800124",
                "brand": "Fresh Farm",
                "categoryName": "Fresh Produce",
                "package_size": "500g",
                "image": None,
            },
        ],
    },
    "l192": {
        "data": {
            "searchProduct": {
                "items": [
                    {
                        "id": "l192_501",
                        "title": "Electric Kettle 1.8L",
                        "price": 9.90,
                        "discount_percentage": 17,
                        "brand_name": "Philips",
                        "supplier_name": "Appliances",
                        "picture_responsive": "https://l192.com/kettle.jpg",
                        "stock_status_label": "In Stock",
                    },
                    {
                        "id": "l192_502",
                        "title": "Non-Stick Frying Pan 28cm",
                        "price": 6.50,
                        "discount_percentage": 0,
                        "brand_name": "Tefal",
                        "supplier_name": "Cookware",
                        "picture_responsive": None,
                        "stock_status_label": "In Stock",
                    },
                ],
            },
        },
    },
    "communitypharma": [
        {
            "id": "pharma_01",
            "name": "Paracetamol 500mg 100 Tablets",
            "price_usd": 2.20,
            "barcode": "8850061001",
            "manufacturer": "Panadol",
            "category": "Pain Relief",
            "dosage_form": "Tablet",
        },
        {
            "id": "pharma_02",
            "name": "Vitamin C 1000mg Effervescent 10s",
            "price_usd": 3.80,
            "barcode": "8850061002",
            "manufacturer": "Redoxon",
            "category": "Vitamins",
            "dosage_form": "Effervescent",
        },
    ],
    "samnangshop": [
        {
            "id": 5082,
            "name": "iPhone 17Pro Max LL/A (2eSim)",
            "sku": "SAMNANG-IPHONE17PM",
            "permalink": "https://khmersamnang.com/product/iphone-17pro-max-ll-a-2esim-copy/",
            "description": "<p>The iPhone 17 Pro Max features a 6.9-inch Super Retina display.</p>",
            "short_description": "<p>6.9-inch Super Retina display.</p>",
            "prices": {
                "price": "1235",
                "regular_price": "1235",
                "sale_price": "1235",
                "currency_code": "USD",
                "currency_minor_unit": 0,
            },
            "categories": [
                {"id": 10, "name": "Apple", "slug": "apple"},
                {"id": 12, "name": "Smartphones", "slug": "smartphones"},
            ],
            "images": [{"src": "https://khmersamnang.com/phone.png"}],
        },
        {
            "id": 5083,
            "name": "Samsung Galaxy S25 Ultra 5G",
            "sku": "SAMNANG-S25U-256",
            "permalink": "https://khmersamnang.com/product/samsung-galaxy-s25-ultra/",
            "description": "<p>Samsung Galaxy S25 Ultra 5G with Snapdragon 8 Elite.</p>",
            "prices": {
                "price": "1249",
                "regular_price": "1249",
                "currency_code": "USD",
                "currency_minor_unit": 0,
            },
            "categories": [
                {"id": 20, "name": "Samsung", "slug": "samsung"},
                {"id": 12, "name": "Smartphones", "slug": "smartphones"},
            ],
            "images": [{"src": "https://khmersamnang.com/s25.png"}],
        },
    ],
    "cellcard": """
    <html><head><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"plans":[{"id":"c1","name":"AO Mobile 5G Monthly 30GB","price":5.00,"type":"Mobile Prepaid","data_allowance":"30GB"},{"id":"c2","name":"Serey Plan Weekly 10GB","price":1.50,"type":"Mobile Prepaid","data_allowance":"10GB"}]}}}
    </script></head><body></body></html>
    """,
    "cellcard_wifi": """
    <html><head><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"plans":[{"id":"cw1","name":"Home Fiber 50 Mbps Monthly","price":18.00,"speed":"50Mbps"},{"id":"cw2","name":"Home Fiber 100 Mbps Monthly","price":28.00,"speed":"100Mbps"}]}}}
    </script></head><body></body></html>
    """,
    "smart": """
    <html><head><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"plans":[{"id":"s1","name":"Smart Laor! 8GB Weekly","price":1.50,"type":"Mobile Data","data_allowance":"8GB"},{"id":"s2","name":"Smart Flexi 30GB Monthly","price":6.00,"type":"Mobile Data","data_allowance":"30GB"}]}}}
    </script></head><body></body></html>
    """,
    "smart_wifi": """
    <html><head><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"plans":[{"id":"sw1","name":"Smart @Home Wireless 30 Mbps","price":15.00,"speed":"30Mbps"},{"id":"sw2","name":"Smart Fiber+ 80 Mbps","price":24.00,"speed":"80Mbps"}]}}}
    </script></head><body></body></html>
    """,
    "khmer24": """
    <html><head><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"listings":[{"id":"k24_01","title":"1 Bedroom Condo BKK1 Rent","price":450.00,"category":"Condo Rental","bedrooms":1,"area_m2":45,"image":"https://khmer24.com/condo.jpg"},{"id":"k24_02","title":"2 Bedroom Apartment TTP","price":350.00,"category":"Apartment Rental","bedrooms":2,"area_m2":70,"image":null}]}}}
    </script></head><body></body></html>
    """,
    "realestate": """
    <html><head><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"listings":[{"id":"re_01","title":"Modern Studio Tonle Bassac","price":400.00,"category":"Studio Rental","bedrooms":1,"area_m2":38,"image":"https://realestate.com.kh/studio.jpg"},{"id":"re_02","title":"3 Bedroom Villa Sen Sok","price":900.00,"category":"Villa Rental","bedrooms":3,"area_m2":180,"image":null}]}}}
    </script></head><body></body></html>
    """,
    "redbus": """
    <html><body>
    <table>
        <tr><th>Cheapest Bus Tickets</th><td>USD 10.00</td></tr>
        <tr><th>Avg. Bus Duration</th><td>5 hrs 45 mins</td></tr>
        <tr><th>First Bus & Last Bus</th><td>01:00 & 23:59</td></tr>
        <tr><th>Daily Bus Services</th><td>248 buses</td></tr>
    </table>
    </body></html>
    """,
    "sokhahotel": {
        "hotels": [
            {
                "rooms": [
                    {
                        "name": "Deluxe Room River View",
                        "price": 95.00,
                        "currency": "USD",
                        "room_type": "Deluxe",
                        "occupancy": 2,
                    },
                    {
                        "name": "Executive Suite",
                        "price": 180.00,
                        "currency": "USD",
                        "room_type": "Suite",
                    },
                ]
            }
        ],
    },
    "bayonbkk_html": """
    <html><head>
    <script>window.__PROVIDER_PROPS__ = {"Apollo": {"RestaurantProduct:1":{"name":"Pork Fried Rice (Bai Cha)","price":3.25,"category":"Khmer Dining"},"RestaurantProduct:2":{"name":"Iced Milk Coffee","price":1.75,"category":"Beverages"}}};
    </script></head><body></body></html>
    """,
    "mef_fx": {"rate": 4050.0, "usd_khr": 4050.0},
}


def _mock_all_http(monkeypatch):
    """Route all HTTP calls to canned data based on URL patterns."""

    def _get(url, **kwargs):
        url_str = str(url)
        if "arystorephone.com" in url_str:
            page = (kwargs.get("params") or {}).get("page", 1)
            return _FakeResponse(_arystore_page(page))
        if "aeononlineshopping.com" in url_str and (
            "aeon1" in url_str or "aeon-1" in url_str
        ):
            return _FakeResponse(_CANNED["aeon"])
        if "aeononlineshopping.com" in url_str and (
            "aeon3" in url_str or "aeon-3" in url_str
        ):
            return _FakeResponse(_CANNED["aeon3"])
        if "delishop.asia" in url_str:
            return _FakeResponse(_CANNED["delishop"])
        if "khmersamnang.com" in url_str:
            return _FakeResponse(_CANNED["samnangshop"])
        if "cellcard.com.kh" in url_str and "home-internet" in url_str:
            return _FakeResponse({}, text=_CANNED["cellcard_wifi"])
        if "cellcard.com.kh" in url_str:
            return _FakeResponse({}, text=_CANNED["cellcard"])
        if "smart.com.kh" in url_str and (
            "home-internet" in url_str
            or "at-home" in url_str
            or "smart-fiber" in url_str
            or "5g-at-home" in url_str
        ):
            return _FakeResponse({}, text=_CANNED["smart_wifi"])
        if "smart.com.kh" in url_str:
            return _FakeResponse({}, text=_CANNED["smart"])
        if "khmer24.com" in url_str:
            return _FakeResponse({}, text=_CANNED["khmer24"])
        if "realestate.com.kh" in url_str:
            return _FakeResponse({}, text=_CANNED["realestate"])
        if "redbus.com.kh" in url_str:
            return _FakeResponse({}, text=_CANNED["redbus"])
        if "sokhahotels" in url_str or "hopenapi" in url_str:
            return _FakeResponse(_CANNED["sokhahotel"])
        if "foodpanda" in url_str or "bayon" in url_str:
            return _FakeResponse({}, text=_CANNED["bayonbkk_html"])
        if "mef.gov.kh" in url_str:
            return _FakeResponse(_CANNED["mef_fx"])
        if "communitypharma.com.kh" in url_str and "assets/" in url_str:
            return _FakeResponse(
                {}, text="var x='eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSJ9.test';"
            )
        if "communitypharma.com.kh" in url_str:
            return _FakeResponse(
                {}, text="<html><script src='/assets/index-abc123.js'></script></html>"
            )
        return _FakeResponse([], status_code=404)

    def _post(url, **kwargs):
        url_str = str(url)
        if "graph-fs.l192.com" in url_str:
            return _FakeResponse(_CANNED["l192"])
        if "graphql.moc.gov.kh" in url_str:
            return _FakeResponse(
                {"data": {"publicCommodityPriceLineReport": {"items": []}}}
            )
        return _FakeResponse([], status_code=404)

    def _requests_get(url, **kwargs):
        url_str = str(url)
        if "supabase.co" in url_str and "rest/v1" in url_str:
            return _FakeResponse(_CANNED["communitypharma"])
        return _get(url, **kwargs)

    def _requests_post(url, **kwargs):
        return _post(url, **kwargs)

    def _cffi_get(url, **kwargs):
        return _get(url, **kwargs)

    def _cffi_post(url, **kwargs):
        return _post(url, **kwargs)

    import scrapers.sources as src_mod

    monkeypatch.setattr(src_mod, "_cffi_get", _cffi_get)
    monkeypatch.setattr(src_mod, "_cffi_post", _cffi_post)
    monkeypatch.setattr(requests, "get", _requests_get)
    monkeypatch.setattr(requests, "post", _requests_post)

    # For AryStore which uses Session.get — patch Session.get to route through our mock
    _orig_session_get = requests.Session.get

    def _session_get(self, url, **kwargs):
        return _get(url, **kwargs)

    monkeypatch.setattr(requests.Session, "get", _session_get)

    # For MOC — mock _query_line_report directly
    def fake_moc_query(self, start_date, end_date, province_id, product_ids):
        return [
            {
                "data": [
                    {"x": "17 Aug, 2026", "y": "5000"},
                    {"x": "18 Aug, 2026", "y": "5100"},
                ]
            },
            {"data": [{"x": "18 Aug, 2026", "y": "4100"}]},
            {"data": [{"x": "18 Aug, 2026", "y": "4000"}]},
        ]

    monkeypatch.setattr(
        src_mod.MocGasolineScraper, "_query_line_report", fake_moc_query
    )

    # For CommunityPharma — mock _extract_dynamic_key
    def fake_extract_key(self):
        return "fake-anon-key"

    monkeypatch.setattr(
        src_mod.CommunityPharmaScraper, "_extract_dynamic_key", fake_extract_key
    )


# ── Tests ──────────────────────────────────────────────────────────────────


def test_scraper_registry_complete():
    expected_sources = [
        "aeon",
        "aeon3",
        "delishop",
        "l192",
        "communitypharma",
        "samnangshop",
        "cellcard",
        "cellcard_wifi",
        "smart",
        "smart_wifi",
        "khmer24",
        "realestate",
        "redbus",
        "bookmebus",
        "sokhahotel",
        "hyyathotel",
        "bayonbkk",
        "mef_fx",
        "new_gasoline",
        "arystore",
    ]
    for src in expected_sources:
        assert src in SCRAPER_REGISTRY, f"Missing scraper source in registry: {src}"
    assert len(SCRAPER_REGISTRY) == 20


@pytest.mark.parametrize("source_slug,scraper_cls", SCRAPER_REGISTRY.items())
def test_all_scrapers_return_valid_records(source_slug, scraper_cls, monkeypatch):
    _mock_all_http(monkeypatch)
    scraper = scraper_cls()
    assert scraper.store_slug == source_slug

    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 8, 17))
    assert isinstance(records, list)
    assert len(records) > 0, f"Scraper '{source_slug}' returned 0 records"

    for r in records:
        assert "scrape_date" in r
        assert "source_slug" in r
        assert r["source_slug"] == source_slug


def test_canonical_record_promo_discount_calc():
    rec = build_canonical_record(
        source_slug="delishop",
        source_type="grocery",
        store_name="Delishop Cambodia",
        item_id="item_01",
        name="Beer Can",
        price=0.90,
        original_price=1.00,
    )
    assert rec["on_promo"] is True
    assert rec["discount_pct"] == 10.0
    assert rec["promo"]["value"] == 0.10


def test_moc_gasoline_scraper_registered():
    scraper = SCRAPER_REGISTRY["new_gasoline"]()
    assert scraper.store_slug == "new_gasoline"
    assert scraper.source_type == "fuel"


def test_moc_gasoline_picks_latest_and_flags_fallback(monkeypatch):
    from scrapers import sources as src_mod

    def fake_query(self, start_date, end_date, province_id, product_ids):
        assert province_id == src_mod.MOC_FUEL_PROVINCE
        # Batch query returns all 3 products in input order
        assert product_ids == [107, 108, 109]
        return [
            {
                "data": [
                    {"x": "14 Aug, 2026", "y": "5000"},
                    {"x": "18 Aug, 2026", "y": "5100"},
                ]
            },
            {"data": [{"x": "18 Aug, 2026", "y": "4100"}]},
            {"data": [{"x": "18 Aug, 2026", "y": "4000"}]},
        ]

    monkeypatch.setattr(src_mod.MocGasolineScraper, "_query_line_report", fake_query)
    scraper = src_mod.MocGasolineScraper()

    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 8, 18))
    assert len(records) == 3
    by_name = {r["name"]: r for r in records}
    assert by_name["Regular Gasoline"]["price"] == 5100.0
    assert by_name["Regular Gasoline"]["currency"] == "KHR"
    assert by_name["Regular Gasoline"]["is_fallback"] is False
    assert by_name["Regular Gasoline"]["attrs"]["price_date"] == "2026-08-18"

    weekend = scraper.fetch_records(scrape_date=pendulum.date(2026, 8, 15))
    by_name_w = {r["name"]: r for r in weekend}
    assert by_name_w["Regular Gasoline"]["price"] == 5000.0
    assert by_name_w["Regular Gasoline"]["is_fallback"] is True
    assert by_name_w["Regular Gasoline"]["attrs"]["price_date"] == "2026-08-14"


def test_arystore_scraper_registered():
    scraper = SCRAPER_REGISTRY["arystore"]()
    assert scraper.store_slug == "arystore"
    assert scraper.source_type == "electronics"


def test_arystore_scraper_maps_full_product_detail(monkeypatch):
    _mock_all_http(monkeypatch)
    scraper = SCRAPER_REGISTRY["arystore"]()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 8, 17))

    assert len(records) == 2
    assert all(r["source_slug"] == "arystore" for r in records)
    assert all(r["scrape_date"] == "2026-08-17" for r in records)

    by_id = {r["item_id"]: r for r in records}
    phone = by_id["1001"]
    assert phone["name"] == "iPhone 15 Pro 128GB"
    assert phone["price"] == 999.0
    assert phone["original_price"] == 1099.0
    assert phone["currency"] == "USD"
    assert phone["on_promo"] is True
    assert phone["brand"] == "Apple"
    assert phone["category_native"] == "Smartphones"
    assert phone["url"] == "https://arystorephone.com/shop/iphone-15-pro-128gb/"
    assert phone["image_url"].startswith("https://")
    assert phone["attrs"]["is_in_stock"] is True

    charger = by_id["1002"]
    assert charger["price"] == 25.0
    assert charger["on_promo"] is False
    assert charger["brand"] is None


def test_arystore_scraper_paginates_until_empty(monkeypatch):
    from scrapers import sources as src_mod

    def _full_page_product(pid: int) -> dict:
        return {
            "id": pid,
            "name": f"Product {pid}",
            "slug": f"product-{pid}",
            "type": "simple",
            "permalink": f"https://arystorephone.com/shop/product-{pid}/",
            "sku": "",
            "on_sale": False,
            "prices": {
                "price": "10",
                "regular_price": "10",
                "sale_price": "10",
                "price_range": None,
                "currency_code": "USD",
            },
            "description": "",
            "short_description": "",
            "categories": [],
            "tags": [],
            "brands": [],
            "images": [],
            "average_rating": "0",
            "review_count": 0,
            "is_in_stock": True,
            "stock_availability": {},
            "formatted_weight": "N/A",
        }

    calls = []

    def _spy_get(url, **kwargs):
        page = (kwargs.get("params") or {}).get("page", 1)
        calls.append(page)
        if page >= 3:
            return _FakeResponse([])
        return _FakeResponse(
            [_full_page_product(1000 + page * 1000 + i) for i in range(100)]
        )

    def _spy_session_get(self, url, **kwargs):
        return _spy_get(url, **kwargs)

    monkeypatch.setattr(requests.Session, "get", _spy_session_get)
    monkeypatch.setattr(src_mod, "_cffi_get", _spy_get)
    scraper = src_mod.AryStorePhoneScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 8, 17))

    assert calls == [1, 2, 3]
    assert len(records) == 200
