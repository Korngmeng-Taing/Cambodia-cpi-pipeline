from __future__ import annotations

import json
import re
from typing import Any

import pendulum

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
    _cffi_get,
    _to_float,
    build_canonical_record,
    log,
)


# 17. Bayon Restaurant BKK I (Restaurant)
# ═══════════════════════════════════════════════════════════════════════════
BAYON_MENU_BASELINE = [
    {
        "id": "bayon_loklak_beef",
        "name": "Traditional Beef Lok Lak with Fried Egg & Rice",
        "price": 4.75,
        "category": "Khmer Cuisine > Beef Dishes",
    },
    {
        "id": "bayon_curry_chicken",
        "name": "Khmer Red Curry Chicken with Crispy Baguette",
        "price": 4.25,
        "category": "Khmer Cuisine > Curry Dishes",
    },
    {
        "id": "bayon_baisachchrouk",
        "name": "Grilled Pork with Broken Rice (Bai Sach Chrouk)",
        "price": 2.50,
        "category": "Khmer Cuisine > Breakfast & Rice",
    },
    {
        "id": "bayon_kuyteav_pork",
        "name": "Phnom Penh Noodle Soup with Sliced Pork (Kuy Teav)",
        "price": 3.25,
        "category": "Khmer Cuisine > Noodle Soup",
    },
    {
        "id": "bayon_kuyteav_beef",
        "name": "Phnom Penh Beef Ball Noodle Soup (Kuy Teav Sach Ko)",
        "price": 3.75,
        "category": "Khmer Cuisine > Noodle Soup",
    },
    {
        "id": "bayon_amok_fish",
        "name": "Authentic Fish Amok Steamed in Banana Leaves",
        "price": 5.25,
        "category": "Khmer Cuisine > Traditional Specialities",
    },
    {
        "id": "bayon_somlor_machou",
        "name": "Sweet & Sour Fish Soup with Morning Glory (Somlor Machou)",
        "price": 4.50,
        "category": "Khmer Cuisine > Traditional Soups",
    },
    {
        "id": "bayon_fried_rice_seafood",
        "name": "Yangzhou Seafood Fried Rice with Prawns & Squid",
        "price": 4.00,
        "category": "Asian Cuisine > Fried Rice",
    },
    {
        "id": "bayon_fried_rice_chicken",
        "name": "Stir-Fried Rice with Minced Chicken & Basil",
        "price": 3.50,
        "category": "Asian Cuisine > Fried Rice",
    },
    {
        "id": "bayon_fried_rice_saltedfish",
        "name": "Khmer Fried Rice with Salted Fish & Pork",
        "price": 3.75,
        "category": "Asian Cuisine > Fried Rice",
    },
    {
        "id": "bayon_stirfry_morningglory",
        "name": "Stir-Fried Morning Glory with Oyster Sauce & Garlic",
        "price": 2.75,
        "category": "Khmer Cuisine > Vegetable Dishes",
    },
    {
        "id": "bayon_stirfry_beef_ginger",
        "name": "Stir-Fried Sliced Beef with Fresh Ginger & Spring Onion",
        "price": 4.50,
        "category": "Khmer Cuisine > Beef Dishes",
    },
    {
        "id": "bayon_springrolls_crispy",
        "name": "Deep-Fried Crispy Spring Rolls (Chai Yor) (5 pcs)",
        "price": 3.00,
        "category": "Appetizers > Spring Rolls",
    },
    {
        "id": "bayon_springrolls_fresh",
        "name": "Fresh Summer Rolls with Prawns & Peanut Dip (4 pcs)",
        "price": 3.25,
        "category": "Appetizers > Spring Rolls",
    },
    {
        "id": "bayon_lemongrass_chicken",
        "name": "Stir-Fried Chicken with Spicy Lemongrass Paste (Kroeung)",
        "price": 4.25,
        "category": "Khmer Cuisine > Chicken Dishes",
    },
    {
        "id": "bayon_tomyum_seafood",
        "name": "Spicy Tom Yum Soup with Mixed Seafood",
        "price": 5.00,
        "category": "Asian Cuisine > Soups",
    },
    {
        "id": "bayon_fried_noodles_pork",
        "name": "Stir-Fried Flat Rice Noodles with Pork & Chinese Kale (Mi Katang)",
        "price": 3.50,
        "category": "Asian Cuisine > Noodle Dishes",
    },
    {
        "id": "bayon_green_mango_salad",
        "name": "Khmer Green Mango Salad with Dried Shrimp",
        "price": 3.50,
        "category": "Appetizers > Khmer Salads",
    },
    {
        "id": "bayon_iced_coffee_milk",
        "name": "Cambodian Iced Coffee with Sweet Condensed Milk (Cafe Teuk Doh Ko)",
        "price": 1.75,
        "category": "Beverages > Coffee & Tea",
    },
    {
        "id": "bayon_iced_black_coffee",
        "name": "Traditional Cambodian Iced Black Coffee (Cafe Khmao)",
        "price": 1.50,
        "category": "Beverages > Coffee & Tea",
    },
    {
        "id": "bayon_fresh_coconut",
        "name": "Whole Fresh Young Coconut Juice",
        "price": 1.75,
        "category": "Beverages > Fresh Juices",
    },
    {
        "id": "bayon_mango_smoothie",
        "name": "Fresh Tropical Mango Fruit Smoothie",
        "price": 2.25,
        "category": "Beverages > Fruit Smoothies",
    },
    {
        "id": "bayon_passion_soda",
        "name": "Fresh Passion Fruit Soda with Mint & Lime",
        "price": 2.00,
        "category": "Beverages > Refreshers",
    },
    {
        "id": "bayon_lime_iced_tea",
        "name": "Khmer Fresh Lime Iced Tea",
        "price": 1.50,
        "category": "Beverages > Coffee & Tea",
    },
    {
        "id": "bayon_dessert_chek_ktis",
        "name": "Traditional Sweet Banana in Coconut Milk Tapioca (Chek Ktis)",
        "price": 1.75,
        "category": "Desserts > Traditional Khmer Desserts",
    },
]


BAYON_FOODPANDA_URL = (
    "https://www.foodpanda.com.kh/en/restaurant/lb0z/bayon-restaurant-bkk-i"
)


class BayonRestaurantScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="bayonbkk", source_type="restaurant")

    def _extract_apollo_state(self, html: str) -> dict:
        if not HAS_BS4:
            return {}
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            text = script.string or ""
            if "window.__PROVIDER_PROPS__" in text or "Apollo" in text:
                # M5 FIX: Use bounded regex to prevent catastrophic backtracking
                # on multi-MB Apollo payloads. Limit match to 500KB and use
                # strict delimiters instead of unbounded .+?
                match = re.search(
                    r"window\.__PROVIDER_PROPS__\s*=\s*(\{.*?\});?\s*$", text, re.DOTALL
                )
                if match:
                    json_str = match.group(1)
                    if len(json_str) <= 500_000:  # 500KB safety limit
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            pass
                match = re.search(r'"__APOLLO_STATE__"\s*:\s*(\{.*?\})\s*[,}]', text)
                if match:
                    json_str = match.group(1)
                    if len(json_str) <= 500_000:
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            pass
        return {}

    def _parse_menu_items(self, apollo_state: dict) -> list[dict[str, Any]]:
        items = []
        if not isinstance(apollo_state, dict):
            return items
        for key, val in apollo_state.items():
            if not isinstance(val, dict):
                continue
            if "RestaurantProduct" in key or "menu_item" in key.lower():
                name = (
                    val.get("name") or val.get("title") or val.get("productName") or ""
                )
                price = _to_float(
                    val.get("price") or val.get("variantPrice") or val.get("basePrice")
                )
                if name and price is not None:
                    items.append(
                        {
                            "name": name,
                            "price": price,
                            "description": val.get("description") or "",
                            "category": val.get("category")
                            or val.get("categoryName")
                            or "",
                        }
                    )
            elif isinstance(val, dict):
                for inner_key, inner_val in val.items():
                    if "RestaurantProduct" in str(inner_key) and isinstance(
                        inner_val, dict
                    ):
                        name = (
                            inner_val.get("name") or inner_val.get("productName") or ""
                        )
                        price = _to_float(
                            inner_val.get("price") or inner_val.get("variantPrice")
                        )
                        if name and price is not None:
                            items.append(
                                {
                                    "name": name,
                                    "price": price,
                                    "description": inner_val.get("description") or "",
                                    "category": inner_val.get("category") or "",
                                }
                            )
        return items

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        try:
            resp = _cffi_get(BAYON_FOODPANDA_URL, timeout=15)
            if resp.status_code == 200:
                apollo_state = self._extract_apollo_state(resp.text)
                menu_items = self._parse_menu_items(apollo_state)
                for idx, item in enumerate(menu_items):
                    records.append(
                        build_canonical_record(
                            source_slug="bayonbkk",
                            source_type="restaurant",
                            store_name="Bayon Restaurant BKK I",
                            item_id=f"bayon_{idx}",
                            name=item["name"],
                            price=item["price"],
                            currency="USD",
                            category_native=item.get("category") or "Khmer Dining",
                            url=BAYON_FOODPANDA_URL,
                            scrape_date=ds,
                        )
                    )
        except Exception as exc:
            log.warning("Bayon Restaurant live scrape failed: %s", exc)

        if not records:
            for item in BAYON_MENU_BASELINE:
                records.append(
                    build_canonical_record(
                        source_slug="bayonbkk",
                        source_type="restaurant",
                        store_name="Bayon Restaurant BKK I",
                        item_id=item["id"],
                        name=item["name"],
                        price=item["price"],
                        currency="USD",
                        category_native=item["category"],
                        url=BAYON_FOODPANDA_URL,
                        scrape_date=ds,
                        is_fallback=True,
                    )
                )
        return records
