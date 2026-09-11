from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urlencode

import pendulum

import asyncio
import threading

try:
    from playwright.async_api import async_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    THROTTLE_DELAY,
    _cffi_get,
    _to_float,
    build_canonical_record,
    log,
)


# 1. AEON 1 Phnom Penh — Next.js Proxy REST API (Grocery)
# ═══════════════════════════════════════════════════════════════════════════
AEON1_API = (
    "https://aeononlineshopping.com/api/proxy/stores/aeon1-aeon-phnom-penh/products"
)
AEON1_PAGE_SIZE = 100

# 2. AEON 3 Mean Chey — Next.js Proxy REST API (Fashion & Beauty)
# ═══════════════════════════════════════════════════════════════════════════
AEON3_API = (
    "https://aeononlineshopping.com/api/proxy/stores/aeon3-fashion-beauty/products"
)
AEON3_PAGE_SIZE = 100


class AeonApiClient:
    """HTTP client with automatic Playwright browser escalation when 403 Forbidden is met."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.use_playwright = False
        self._warmed_up = False

    def _run_coro(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def get_json(
        self, url: str, params: dict | None = None, timeout: int = 30
    ) -> dict | None:
        if not self.use_playwright:
            try:
                headers = dict(AEON_HEADERS)
                if "aeon3" in url:
                    headers["Referer"] = (
                        "https://aeononlineshopping.com/shop-by-store/aeon3-fashion-beauty?tab=products"
                    )
                else:
                    headers["Referer"] = (
                        "https://aeononlineshopping.com/shop-by-store/aeon1-aeon-phnom-penh?tab=products"
                    )

                # Warm up session once on first call to grab Cloudflare clearance cookies
                if not self._warmed_up:
                    try:
                        _cffi_get(
                            "https://aeononlineshopping.com/",
                            headers=headers,
                            timeout=15,
                        )
                    except Exception:
                        pass
                    self._warmed_up = True

                resp = _cffi_get(url, params=params, headers=headers, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                err_str = str(exc)
                if ("403" in err_str or "Forbidden" in err_str) and HAS_PLAYWRIGHT:
                    log.warning(
                        "Aeon API returned 403 with standard HTTP client. "
                        "Escalating to Async Playwright browser context..."
                    )
                    self._init_playwright()
                else:
                    raise exc

        return self._playwright_fetch(url, params)

    def _init_playwright(self):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright is required to bypass Aeon 403 protection, but not installed."
            )

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.thread.start()

        async def _init():
            self.playwright = await async_playwright().start()
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            }
            # Locate installed Chromium binary downloaded with --no-shell
            import glob
            base_dir = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/home/airflow/.cache/ms-playwright")
            found_chrome = glob.glob(f"{base_dir}/chromium-*/chrome-linux/chrome")
            if found_chrome:
                launch_kwargs["executable_path"] = found_chrome[0]
            else:
                launch_kwargs["channel"] = "chromium"

            self.browser = await self.playwright.chromium.launch(**launch_kwargs)
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-GB",
                timezone_id="Asia/Phnom_Penh",
            )
            self.page = await self.context.new_page()
            try:
                from pipeline.stealth import STEALTH_SCRIPTS

                await self.page.add_init_script(STEALTH_SCRIPTS)
            except Exception:
                pass

            await self.page.goto(
                "https://aeononlineshopping.com",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await asyncio.sleep(2)
            self.use_playwright = True

        self._run_coro(_init())

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _playwright_fetch(self, url: str, params: dict | None = None) -> dict | None:
        async def _fetch():
            query_str = f"?{urlencode(params)}" if params else ""
            full_url = f"{url}{query_str}"
            script = """
            async (targetUrl) => {
                const res = await fetch(targetUrl, {
                    headers: {
                        'Accept': 'application/json, text/plain, */*',
                        'x-language': 'en-gb',
                        'x-currency': 'KHR'
                    }
                });
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
                }
                return await res.json();
            }
            """
            return await self.page.evaluate(script, full_url)

        return self._run_coro(_fetch())

    def close(self):
        if not self.use_playwright or not self.loop:
            return

        async def _close():
            if self.page:
                try:
                    await self.page.close()
                except Exception:
                    pass
            if self.context:
                try:
                    await self.context.close()
                except Exception:
                    pass
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception:
                    pass

        try:
            self._run_coro(_close())
        except Exception:
            pass
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def _build_aeon_category_map(filters: dict) -> dict[int, str]:
    """Flattens the nested AEON category tree into {cat_id: 'Parent > Child > Sub'} map."""
    cat_map = {}

    def _traverse(node: dict, path: list[str]):
        name = node.get("name") or ""
        cur_path = path + [name] if name else path
        node_id = node.get("id")
        if node_id:
            cat_map[node_id] = " > ".join(cur_path)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _traverse(child, cur_path)

    for root in (filters.get("categories") if isinstance(filters, dict) else []):
        if isinstance(root, dict):
            _traverse(root, [])
    return cat_map


def _extract_aeon_category_targets(filters: dict) -> list[tuple[int, str]]:
    """Extracts level-2 (or level-1 if no children) category targets to query via categoryIds.
    This guarantees that every returned product is stamped with its true specific category
    (e.g. 'Grocery > Beer', 'Health & Hygiene > Cleaning liquid', 'Household > Kitchen')
    rather than a blanket fallback like 'Grocery'.
    """
    targets: list[tuple[int, str]] = []
    roots = filters.get("categories") if isinstance(filters, dict) else []
    for root in (roots or []):
        if not isinstance(root, dict) or not root.get("id"):
            continue
        r_id = root["id"]
        r_name = root.get("name") or ""
        # Skip purely generic marketing/event banners if specific subcategories exist
        if r_name.lower() in ("special offer up to 50% off", "event"):
            continue
        children = root.get("children") or []
        if children:
            for child in children:
                if isinstance(child, dict) and child.get("id"):
                    c_id = child["id"]
                    c_name = child.get("name") or ""
                    targets.append((c_id, f"{r_name} > {c_name}"))
        else:
            targets.append((r_id, r_name))
    return targets


AEON_MAX_PAGES = int(os.environ.get("AEON_MAX_PAGES", "0"))


AEON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-GB,en;q=0.9,km-KH;q=0.8,km;q=0.7",
    "Origin": "https://aeononlineshopping.com",
    "Referer": "https://aeononlineshopping.com/shop-by-store/aeon1-aeon-phnom-penh?tab=products",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "x-requested-with": "XMLHttpRequest",
    "x-language": "en-gb",
    "x-currency": "KHR",
}


class AeonSupermarketScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="aeon", source_type="grocery")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        with AeonApiClient() as client:
            # Step 1: Discover category hierarchy from initial probe
            targets: list[tuple[int, str]] = []
            cat_map: dict[int, str] = {}
            for attempt in range(4):
                try:
                    probe_body = client.get_json(
                        AEON1_API,
                        params={"page": 1, "limit": 10},
                        timeout=30,
                    )
                    if probe_body and isinstance(probe_body.get("filters"), dict):
                        cat_map = _build_aeon_category_map(probe_body["filters"])
                        targets = _extract_aeon_category_targets(probe_body["filters"])
                    break
                except Exception:
                    time.sleep(1.5 * (attempt + 1))

            # Fallback to single stream if category filter tree was not discovered
            if not targets:
                targets = [(None, "Grocery")]

            for cat_id, cat_path in targets:
                page = 1
                total_pages = 999
                consecutive_errors = 0
                while page <= total_pages:
                    if AEON_MAX_PAGES > 0 and page > AEON_MAX_PAGES:
                        break
                    params = {"page": page, "limit": AEON1_PAGE_SIZE}
                    if cat_id:
                        params["categoryIds"] = cat_id

                    body = None
                    for attempt in range(5):
                        try:
                            body = client.get_json(
                                AEON1_API,
                                params=params,
                                timeout=30,
                            )
                            if body:
                                break
                        except Exception as exc:
                            if attempt < 4:
                                time.sleep(1.5 * (attempt + 1))
                            else:
                                log.warning("AEON1 cat %s page %d error: %s", cat_path, page, exc)

                    if not body:
                        consecutive_errors += 1
                        if consecutive_errors >= 3:
                            break
                        page += 1
                        time.sleep(1.5)
                        continue

                    consecutive_errors = 0
                    prod_obj = body.get("products", {})
                    if isinstance(prod_obj, dict):
                        products = prod_obj.get("data", [])
                        meta = prod_obj.get("meta", {})
                        tp = meta.get("totalPages")
                        if tp is None:
                            tp = prod_obj.get("lastPage")
                        if tp is not None:
                            total_pages = tp
                    elif isinstance(prod_obj, list):
                        products = prod_obj
                        total_pages = body.get("totalPages", page)
                    else:
                        products = body.get("data", [])

                    if not products:
                        break

                    for p in products:
                        if not isinstance(p, dict):
                            continue
                        p_id = str(p.get("id", ""))
                        if not p_id or p_id in seen_ids:
                            continue
                        seen_ids.add(p_id)

                        price = _to_float(p.get("salePrice") or p.get("price"))
                        if price is None:
                            continue
                        orig = _to_float(
                            p.get("fullPriceBeforeDiscount") or p.get("originalPrice")
                        )
                        on_sale = bool(p.get("discount") or (orig and orig > price))

                        # Use verified category path from the target query, or category map
                        item_cat_id = p.get("categoryId") or cat_id
                        item_cat_name = cat_map.get(item_cat_id) or cat_path or "Grocery"

                        records.append(
                            build_canonical_record(
                                source_slug="aeon",
                                source_type="grocery",
                                store_name="AEON 1 Phnom Penh",
                                item_id=p_id,
                                name=p.get("name") or p.get("title") or "",
                                price=price,
                                currency="KHR",
                                original_price=orig,
                                barcode=p.get("barcode"),
                                brand=p.get("brand"),
                                category_native=item_cat_name,
                                package_size=p.get("size") or p.get("net_weight") or p.get("volume"),
                                url=p.get("url")
                                or f"https://aeononlineshopping.com/product/{p_id}",
                                image_url=p.get("image")
                                or p.get("imageUrl")
                                or (
                                    (p.get("galleries") or [{}])[0].get("url")
                                    if p.get("galleries")
                                    else None
                                ),
                                scrape_date=ds,
                                on_promo=on_sale,
                                attrs={"badges": p.get("badges") or []},
                            )
                        )
                    if len(products) < AEON1_PAGE_SIZE:
                        break
                    page += 1
                    time.sleep(THROTTLE_DELAY)

        if not records:
            raise RuntimeError(f"AEON1: 0 products scraped on {ds}")
        return records


class AeonFashionScraper(BaseScraper):
    def __init__(self):
        super().__init__(store_slug="aeon3", source_type="fashion")

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        with AeonApiClient() as client:
            # Step 1: Discover category hierarchy from initial probe
            targets: list[tuple[int, str]] = []
            cat_map: dict[int, str] = {}
            for attempt in range(4):
                try:
                    probe_body = client.get_json(
                        AEON3_API,
                        params={"page": 1, "limit": 10},
                        timeout=30,
                    )
                    if probe_body and isinstance(probe_body.get("filters"), dict):
                        cat_map = _build_aeon_category_map(probe_body["filters"])
                        targets = _extract_aeon_category_targets(probe_body["filters"])
                    break
                except Exception:
                    time.sleep(1.5 * (attempt + 1))

            if not targets:
                targets = [(None, "Fashion & Beauty")]

            for cat_id, cat_path in targets:
                page = 1
                total_pages = 999
                consecutive_errors = 0
                while page <= total_pages:
                    if AEON_MAX_PAGES > 0 and page > AEON_MAX_PAGES:
                        break
                    params = {"page": page, "limit": AEON3_PAGE_SIZE}
                    if cat_id:
                        params["categoryIds"] = cat_id

                    body = None
                    for attempt in range(5):
                        try:
                            body = client.get_json(
                                AEON3_API,
                                params=params,
                                timeout=30,
                            )
                            if body:
                                break
                        except Exception as exc:
                            if attempt < 4:
                                time.sleep(1.5 * (attempt + 1))
                            else:
                                log.warning("AEON3 cat %s page %d error: %s", cat_path, page, exc)

                    if not body:
                        consecutive_errors += 1
                        if consecutive_errors >= 3:
                            break
                        page += 1
                        time.sleep(1.5)
                        continue

                    consecutive_errors = 0
                    prod_obj = body.get("products", {})
                    if isinstance(prod_obj, dict):
                        products = prod_obj.get("data", [])
                        meta = prod_obj.get("meta", {})
                        tp = meta.get("totalPages")
                        if tp is None:
                            tp = prod_obj.get("lastPage")
                        if tp is not None:
                            total_pages = tp
                    elif isinstance(prod_obj, list):
                        products = prod_obj
                        total_pages = body.get("totalPages", page)
                    else:
                        products = body.get("data", [])

                    if not products:
                        break

                    for p in products:
                        if not isinstance(p, dict):
                            continue
                        p_id = str(p.get("id", ""))
                        if not p_id or p_id in seen_ids:
                            continue
                        seen_ids.add(p_id)

                        price = _to_float(p.get("salePrice") or p.get("price"))
                        if price is None:
                            continue
                        orig = _to_float(
                            p.get("fullPriceBeforeDiscount") or p.get("originalPrice")
                        )
                        on_sale = bool(p.get("discount") or (orig and orig > price))

                        item_cat_id = p.get("categoryId") or cat_id
                        item_cat_name = cat_map.get(item_cat_id) or cat_path or "Fashion & Beauty"

                        records.append(
                            build_canonical_record(
                                source_slug="aeon3",
                                source_type="fashion",
                                store_name="AEON 3 Mean Chey",
                                item_id=p_id,
                                name=p.get("name") or p.get("title") or "",
                                price=price,
                                currency="KHR",
                                original_price=orig,
                                barcode=p.get("barcode"),
                                brand=p.get("brand"),
                                category_native=item_cat_name,
                                url=f"https://aeononlineshopping.com/product/{p_id}",
                                image_url=p.get("image")
                                or p.get("imageUrl")
                                or (
                                    (p.get("galleries") or [{}])[0].get("url")
                                    if p.get("galleries")
                                    else None
                                ),
                                scrape_date=ds,
                                on_promo=on_sale,
                            )
                        )
                    if len(products) < AEON3_PAGE_SIZE:
                        break
                    page += 1
                    time.sleep(THROTTLE_DELAY)

        if not records:
            raise RuntimeError(f"AEON3: 0 products scraped on {ds}")
        return records
