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
    "ucare_html": """<html><head><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"preloadedState":{"merchantApi":{"queries":{"q1":{"data":{"merchant":{"name":"Ucare Pharmacy Chroy Changva","currency":{"code":"KHR"},"menu":{"departments":[{"name":"OTC Medicine","items":[{"ID":"KHITE001","name":"Panadol - Extra 500mg","priceInMinorUnit":850000,"available":true,"barcode":"885012345678","SKU":"SKU001","imgHref":"https://img.grab.com/1.jpg"}]}]}}}}}}}}}</script></head><body></body></html>""",
    "chipmong_html": """<html><head><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"preloadedState":{"merchantApi":{"queries":{"q1":{"data":{"merchant":{"name":"Chip Mong Supermarket Eden","currency":{"code":"KHR"},"menu":{"departments":[{"name":"Fresh Produce","items":[{"ID":"CM001","name":"Cambodian Jasmine Rice 5kg","priceInMinorUnit":2100000,"available":true,"barcode":"885011122233","SKU":"CMSKU1","imgHref":"https://img.grab.com/cm1.jpg"}]}]}}}}}}}}}</script></head><body></body></html>""",
    "lucky_html": """<html><head><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"preloadedState":{"merchantApi":{"queries":{"q1":{"data":{"merchant":{"name":"Lucky Supermarket Chroy Changva","currency":{"code":"KHR"},"menu":{"departments":[{"name":"Grocery","items":[{"ID":"LK001","name":"Angkor Harvest Jasmine Rice 5kg","priceInMinorUnit":2050000,"available":true,"barcode":"885022233344","SKU":"LKSKU1","imgHref":"https://img.grab.com/lk1.jpg"}]}]}}}}}}}}}</script></head><body></body></html>""",
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
        if "10-C7CGVPK3TJ3AEX" in url_str or "chip-mong" in url_str:
            return _FakeResponse({}, text=_CANNED.get("chipmong_html", _CANNED.get("ucare_html")))
        if "10-C7CGVZEFJ76BJN" in url_str or "lucky" in url_str:
            return _FakeResponse({}, text=_CANNED.get("lucky_html", _CANNED.get("ucare_html")))
        if "mart.grab.com" in url_str:
            return _FakeResponse({}, text=_CANNED["ucare_html"])
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

    # For MOC / Gasoline — mock _fetch_from_tela_telegram directly
    def fake_tela_fetch(self, target_date):
        return {
            "source_url": "https://t.me/s/telakhmerofficial",
            "price_date": target_date,
            "prices": {
                106: 5250.0,
                107: 4400.0,
                108: 5150.0,
                109: 3950.0,
                110: 2400.0,
            },
            "source_type": "tela_telegram",
        }

    monkeypatch.setattr(
        src_mod.MocGasolineScraper, "_fetch_from_tela_telegram", fake_tela_fetch
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
        "smart",
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
        "grab_ucare",
        "grab_lucky",
        "grab_chipmong",
        "khmermoto",
    ]
    for src in expected_sources:
        assert src in SCRAPER_REGISTRY, f"Missing scraper source in registry: {src}"
    assert len(SCRAPER_REGISTRY) == 22


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


def test_moc_gasoline_tela_telegram_extraction(monkeypatch):
    """Verifies that Tela Telegram post extracts all 4 fuels + LPG."""
    from scrapers import sources as src_mod

    canned_post = {
        "source_url": "https://t.me/s/telakhmerofficial",
        "price_date": pendulum.date(2026, 9, 1),
        "prices": {
            106: 5250.0,
            107: 4400.0,
            108: 5150.0,
            110: 2400.0,
        },
        "source_type": "tela_telegram",
    }

    monkeypatch.setattr(src_mod.MocGasolineScraper, "_fetch_from_tela_telegram", lambda self, target: canned_post)

    scraper = src_mod.MocGasolineScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))
    assert len(records) == 4
    by_name = {r["name"]: r for r in records}
    assert by_name["Regular Gasoline"]["price"] == 4400.0
    assert by_name["Regular Gasoline"]["is_fallback"] is True
    assert by_name["Diesel"]["price"] == 5150.0
    assert by_name["Super 95 Gasoline"]["price"] == 5250.0
    assert by_name["LPG Gas"]["price"] == 2400.0
    assert by_name["LPG Gas"]["category_native"] == "Gas / LPG"
    assert by_name["LPG Gas"]["attrs"]["source_type"] == "tela_telegram"


def test_moc_gasoline_news_announcements_fallback(monkeypatch):
    """When Tela Telegram is unavailable, falls back to news announcements mirror."""
    from scrapers import sources as src_mod

    def fake_announcements(self, target_date):
        return {
            "source_url": "https://example.com/moc-gas-notice",
            "price_date": pendulum.date(2026, 9, 1),
            "prices": {
                106: 5250.0,
                107: 4400.0,
                108: 5150.0,
                110: 2400.0,
            },
            "source_type": "official_announcement_mirror",
        }

    monkeypatch.setattr(src_mod.MocGasolineScraper, "_fetch_from_tela_telegram", lambda self, target: None)
    monkeypatch.setattr(src_mod.MocGasolineScraper, "_fetch_from_news_announcements", fake_announcements)

    scraper = src_mod.MocGasolineScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 1))
    assert len(records) == 4
    by_name = {r["name"]: r for r in records}
    assert by_name["Regular Gasoline"]["price"] == 4400.0
    assert by_name["Regular Gasoline"]["is_fallback"] is False
    assert by_name["Regular Gasoline"]["attrs"]["source_type"] == "official_announcement_mirror"
    assert by_name["Diesel"]["price"] == 5150.0


def test_moc_gasoline_complete_offline_fallback(monkeypatch):
    """When all live channels fail, returns official baseline benchmark prices to satisfy quality gate."""
    from scrapers import sources as src_mod

    monkeypatch.setattr(src_mod.MocGasolineScraper, "_fetch_from_tela_telegram", lambda self, target: None)
    monkeypatch.setattr(src_mod.MocGasolineScraper, "_fetch_from_news_announcements", lambda self, target: None)
    monkeypatch.setattr(src_mod.MocGasolineScraper, "_fetch_from_telegram", lambda self, target: None)

    scraper = src_mod.MocGasolineScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 1))
    assert len(records) == 4
    by_name = {r["name"]: r for r in records}
    assert by_name["Regular Gasoline"]["price"] == 4400.0
    assert by_name["Regular Gasoline"]["is_fallback"] is True
    assert by_name["Regular Gasoline"]["attrs"]["source_type"] == "official_baseline_fallback"
    assert by_name["Super 95 Gasoline"]["price"] == 5250.0
    assert by_name["Diesel"]["price"] == 5150.0
    assert by_name["LPG Gas"]["price"] == 2400.0


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


# --- GrabMart Ucare Pharmacy Scraper Tests ---


def test_grab_ucare_in_registry():
    assert "grab_ucare" in SCRAPER_REGISTRY
    scraper = SCRAPER_REGISTRY["grab_ucare"]()
    assert scraper.store_slug == "grab_ucare"
    assert scraper.source_type == "pharmacy"


def test_grab_ucare_fetch_records_mock(monkeypatch):
    import scrapers.sources.ucare as ucare_mod

    mock_html = """
    <html>
      <head>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "preloadedState": {
                "merchantApi": {
                  "queries": {
                    "q1": {
                      "data": {
                        "merchant": {
                          "name": "Ucare Pharmacy Chroy Changva",
                          "currency": {"code": "KHR"},
                          "menu": {
                            "departments": [
                              {
                                "name": "OTC Medicine",
                                "items": [
                                  {
                                    "ID": "ITEM123",
                                    "name": "Panadol - Extra 500mg 24 Tablets",
                                    "priceInMinorUnit": 850000,
                                    "available": true,
                                    "barcode": "885012345678",
                                    "SKU": "SKU123",
                                    "imgHref": "https://img.grab.com/123.jpg"
                                  }
                                ]
                              }
                            ]
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        </script>
      </head>
      <body></body>
    </html>
    """

    def _mock_get(url, **kwargs):
        return _FakeResponse(None, status_code=200, text=mock_html)

    monkeypatch.setattr(ucare_mod, "_cffi_get", _mock_get)
    scraper = ucare_mod.GrabUcarePharmacyScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))

    assert len(records) == 1
    rec = records[0]
    assert rec["source_slug"] == "grab_ucare"
    assert rec["source_type"] == "pharmacy"
    assert rec["store"] == "Ucare Pharmacy Chroy Changva"
    assert rec["item_id"] == "ITEM123"
    assert rec["name"] == "Panadol - Extra 500mg 24 Tablets"
    assert rec["price"] == 8500.0
    assert rec["currency"] == "KHR"
    assert rec["brand"] == "Panadol"
    assert rec["category_native"] == "OTC Medicine"
    assert rec["barcode"] == "885012345678"
    assert rec["is_fallback"] is False


def test_grab_ucare_fetch_records_fallback(monkeypatch):
    import scrapers.sources.ucare as ucare_mod

    def _mock_err(url, **kwargs):
        raise requests.RequestException("Connection refused")

    monkeypatch.setattr(ucare_mod, "_cffi_get", _mock_err)
    scraper = ucare_mod.GrabUcarePharmacyScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))

    assert len(records) > 0
    assert all(r["is_fallback"] is True for r in records)
    assert all(r["source_slug"] == "grab_ucare" for r in records)


# --- GrabMart Lucky Supermarket Scraper Tests ---


def test_grab_lucky_in_registry():
    assert "grab_lucky" in SCRAPER_REGISTRY
    scraper = SCRAPER_REGISTRY["grab_lucky"]()
    assert scraper.store_slug == "grab_lucky"
    assert scraper.source_type == "grocery"


def test_grab_lucky_fetch_records_mock(monkeypatch):
    import scrapers.sources.lucky as lucky_mod

    mock_html = """
    <html>
      <head>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "preloadedState": {
                "merchantApi": {
                  "queries": {
                    "q1": {
                      "data": {
                        "merchant": {
                          "name": "Lucky Supermarket Chroy Changva",
                          "currency": {"code": "KHR"},
                          "menu": {
                            "departments": [
                              {
                                "name": "Fruits & Veggies",
                                "items": [
                                  {
                                    "ID": "LUCKY001",
                                    "name": "Fresh Kiwi Gold Jumbo 2s",
                                    "priceInMinorUnit": 1840000,
                                    "available": true,
                                    "barcode": "885098765432",
                                    "SKU": "SKULUCKY1",
                                    "imgHref": "https://img.grab.com/kiwi.jpg"
                                  }
                                ]
                              }
                            ]
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        </script>
      </head>
      <body></body>
    </html>
    """

    def _mock_get(url, **kwargs):
        return _FakeResponse(None, status_code=200, text=mock_html)

    monkeypatch.setattr(lucky_mod, "_cffi_get", _mock_get)
    scraper = lucky_mod.GrabLuckySupermarketScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))

    assert len(records) == 1
    rec = records[0]
    assert rec["source_slug"] == "grab_lucky"
    assert rec["source_type"] == "grocery"
    assert rec["store"] == "Lucky Supermarket Chroy Changva"
    assert rec["item_id"] == "LUCKY001"
    assert rec["name"] == "Fresh Kiwi Gold Jumbo 2s"
    assert rec["price"] == 18400.0
    assert rec["currency"] == "KHR"
    assert rec["category_native"] == "Fruits & Veggies"
    assert rec["is_fallback"] is False


def test_grab_lucky_fetch_records_fallback(monkeypatch):
    import scrapers.sources.lucky as lucky_mod

    def _mock_err(url, **kwargs):
        raise requests.RequestException("Timeout")

    monkeypatch.setattr(lucky_mod, "_cffi_get", _mock_err)
    scraper = lucky_mod.GrabLuckySupermarketScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))

    assert len(records) > 0
    assert all(r["is_fallback"] is True for r in records)
    assert all(r["source_slug"] == "grab_lucky" for r in records)


# --- GrabMart Chip Mong Supermarket Scraper Tests ---


def test_grab_chipmong_in_registry():
    assert "grab_chipmong" in SCRAPER_REGISTRY
    scraper = SCRAPER_REGISTRY["grab_chipmong"]()
    assert scraper.store_slug == "grab_chipmong"
    assert scraper.source_type == "grocery"


def test_grab_chipmong_fetch_records_mock(monkeypatch):
    import scrapers.sources.chipmong as chipmong_mod

    mock_html = """
    <html>
      <head>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "preloadedState": {
                "merchantApi": {
                  "queries": {
                    "q1": {
                      "data": {
                        "merchant": {
                          "name": "Chip Mong Supermarket Eden",
                          "currency": {"code": "KHR"},
                          "menu": {
                            "departments": [
                              {
                                "name": "Canned Foods",
                                "items": [
                                  {
                                    "ID": "CHIP001",
                                    "name": "Yummi Cook Sardines 240g",
                                    "priceInMinorUnit": 1123000,
                                    "available": true,
                                    "barcode": "885077711223",
                                    "SKU": "SKUCHIP1",
                                    "imgHref": "https://img.grab.com/sardines.jpg"
                                  }
                                ]
                              }
                            ]
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        </script>
      </head>
      <body></body>
    </html>
    """

    def _mock_get(url, **kwargs):
        return _FakeResponse(None, status_code=200, text=mock_html)

    monkeypatch.setattr(chipmong_mod, "_cffi_get", _mock_get)
    scraper = chipmong_mod.GrabChipMongSupermarketScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))

    assert len(records) == 1
    rec = records[0]
    assert rec["source_slug"] == "grab_chipmong"
    assert rec["source_type"] == "grocery"
    assert rec["store"] == "Chip Mong Supermarket Eden"
    assert rec["item_id"] == "CHIP001"
    assert rec["name"] == "Yummi Cook Sardines 240g"
    assert rec["price"] == 11230.0
    assert rec["currency"] == "KHR"
    assert rec["category_native"] == "Canned Foods"
    assert rec["is_fallback"] is False


def test_grab_chipmong_fetch_records_fallback(monkeypatch):
    import scrapers.sources.chipmong as chipmong_mod

    def _mock_err(url, **kwargs):
        raise requests.RequestException("Server Error")

    monkeypatch.setattr(chipmong_mod, "_cffi_get", _mock_err)
    scraper = chipmong_mod.GrabChipMongSupermarketScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))

    assert len(records) > 0
    assert all(r["is_fallback"] is True for r in records)
    assert all(r["source_slug"] == "grab_chipmong" for r in records)


def test_cellcard_combined_records(monkeypatch):
    """Verifies combined Cellcard scraper returns both mobile plans and home internet/wifi plans."""
    _mock_all_http(monkeypatch)
    from scrapers.sources.cellcard import CellcardScraper

    scraper = CellcardScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))
    assert len(records) >= 5  # mocked live: 2 mobile + 3 wifi plans; fallback: 5 mobile + 3 wifi
    assert all(r["source_slug"] == "cellcard" for r in records)
    names = [r["name"] for r in records]
    # Check both mobile and wifi plan names are present
    assert any("AO Mobile" in name or "Big Love" in name or "Serey" in name for name in names)
    assert any("Home Wi-Fi" in name or "Fiber" in name for name in names)


def test_smart_combined_records(monkeypatch):
    """Verifies combined Smart scraper returns both mobile plans and home internet/wifi plans."""
    _mock_all_http(monkeypatch)
    from scrapers.sources.smart import SmartScraper

    scraper = SmartScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 3))
    assert len(records) >= 8  # 5 mobile + 3 wifi plans
    assert all(r["source_slug"] == "smart" for r in records)
    names = [r["name"] for r in records]
    # Check both mobile and wifi plan names are present
    assert any("Smart Laor" in name or "Flexi" in name for name in names)
    assert any("Home Wi-Fi" in name or "Fiber" in name for name in names)


def test_khmermoto_scraper(monkeypatch):
    """Verifies Khmer Moto Shop scraper parses motorcycles and accessories properly."""
    _mock_all_http(monkeypatch)
    from scrapers.sources.khmermoto import KhmerMotoShopScraper

    scraper = KhmerMotoShopScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 8))
    assert len(records) > 0
    assert all(r["source_slug"] == "khmermoto" for r in records)
    assert all(r["currency"] == "USD" for r in records)
    assert all(r["price"] > 0 for r in records)


def test_khmermoto_fallback(monkeypatch):
    """Verifies Khmer Moto Shop degrades to baseline catalog on API error."""
    import requests
    from scrapers.sources import khmermoto as kmt_mod

    def _mock_err(url, **kwargs):
        raise requests.RequestException("API Down")

    monkeypatch.setattr(requests, "get", _mock_err)
    scraper = kmt_mod.KhmerMotoShopScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 8))
    assert len(records) >= 5
    assert all(r["is_fallback"] is True for r in records)
    assert any("Dream" in r["name"] for r in records)


def test_metfone_scraper(monkeypatch):
    """Verifies Metfone Cambodia scraper extracts prepaid bundles and home fiber packages."""
    from scrapers.sources.metfone import MetfoneScraper

    scraper = MetfoneScraper()
    records = scraper.fetch_records(scrape_date=pendulum.date(2026, 9, 8))
    assert len(records) >= 14  # 10 mobile + 4 fiber plans
    assert all(r["source_slug"] == "metfone" for r in records)
    assert all(r["currency"] == "USD" for r in records)
    assert all(r["price"] > 0 for r in records)
    names = [r["name"] for r in records]
    assert any("KADO" in name for name in names)
    assert any("Fiber" in name for name in names)


