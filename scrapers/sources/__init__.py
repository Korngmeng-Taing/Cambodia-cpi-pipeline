"""
scrapers/sources
────────────────
Modular scraper suite (20 sources: 19 retail + MEF FX) adhering to
SCRAPER_METHODOLOGY_GUIDE.md and Schema v1.0.

Modules:
  • aeon.py             – AEON 1 Supermarket & AEON 3 Fashion
  • arystore.py         – Ary Store Phone Shop (WooCommerce REST)
  • bayon.py            – Bayon Restaurant BKK I (Apollo State)
  • bookmebus.py        – BookMeBus Intercity Transport
  • cellcard.py         – Cellcard Mobile & Home Internet/Fiber
  • communitypharma.py  – Community Pharmacy (Supabase PostgREST)
  • delishop.py         – Delishop Grocery API
  • gasoline.py         – MOC Daily Fuel Prices (GraphQL)
  • hyatthotel.py       – Hyatt Regency Hotel
  • khmer24.py          – Khmer24 Real Estate (Housing)
  • l192.py             – L192 Marketplace (GraphQL)
  • mef_fx.py           – MEF Official Daily Exchange Rate (FX)
  • realestate.py       – Realestate.com.kh (Housing)
  • redbus.py           – redBus Cambodia Intercity Transport
  • samnangshop.py      – Khmer Samnang Phone Shop (WooCommerce REST)
  • smart.py            – Smart Mobile & Home Internet/WiFi
  • sokhahotel.py       – Sokha Hotel & Dining
"""

from __future__ import annotations

from scrapers.base import BaseScraper
from scrapers.sources._common import (
    THROTTLE_DELAY,
    _cffi_get,
    _cffi_post,
    _strip_html,
    _to_float,
    build_canonical_record,
)
from scrapers.sources.aeon import AeonFashionScraper, AeonSupermarketScraper
from scrapers.sources.arystore import AryStorePhoneScraper
from scrapers.sources.ucare import GrabUcarePharmacyScraper
from scrapers.sources.lucky import GrabLuckySupermarketScraper
from scrapers.sources.chipmong import GrabChipMongSupermarketScraper
from scrapers.sources.bayon import BayonRestaurantScraper
from scrapers.sources.bookmebus import BookMeBusScraper
from scrapers.sources.cellcard import CellcardMobileScraper, CellcardScraper, CellcardWifiScraper
from scrapers.sources.communitypharma import CommunityPharmaScraper
from scrapers.sources.delishop import DelishopScraper
from scrapers.sources.gasoline import MOC_FUEL_PROVINCE, MocGasolineScraper
from scrapers.sources.hyatthotel import HyattHotelScraper
from scrapers.sources.khmer24 import Khmer24Scraper
from scrapers.sources.l192 import L192Scraper
from scrapers.sources.mef_fx import MefExchangeRateScraper
from scrapers.sources.realestate import RealestateKhScraper
from scrapers.sources.redbus import RedBusKhScraper
from scrapers.sources.samnangshop import SamnangShopScraper
from scrapers.sources.smart import SmartMobileScraper, SmartScraper, SmartWifiScraper
from scrapers.sources.sokhahotel import SokhaHotelScraper
from scrapers.sources.nis_cpi import NISCPIScraper

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "aeon": AeonSupermarketScraper,
    "aeon3": AeonFashionScraper,
    "delishop": DelishopScraper,
    "l192": L192Scraper,
    "communitypharma": CommunityPharmaScraper,
    "samnangshop": SamnangShopScraper,
    "cellcard": CellcardScraper,
    "smart": SmartScraper,
    "khmer24": Khmer24Scraper,
    "realestate": RealestateKhScraper,
    "redbus": RedBusKhScraper,
    "bookmebus": BookMeBusScraper,
    "sokhahotel": SokhaHotelScraper,
    "hyyathotel": HyattHotelScraper,
    "bayonbkk": BayonRestaurantScraper,
    "mef_fx": MefExchangeRateScraper,
    "new_gasoline": MocGasolineScraper,
    "arystore": AryStorePhoneScraper,
    "grab_ucare": GrabUcarePharmacyScraper,
    "grab_lucky": GrabLuckySupermarketScraper,
    "grab_chipmong": GrabChipMongSupermarketScraper,
}

__all__ = [
    "SCRAPER_REGISTRY",
    "AeonSupermarketScraper",
    "AeonFashionScraper",
    "DelishopScraper",
    "L192Scraper",
    "CommunityPharmaScraper",
    "SamnangShopScraper",
    "CellcardScraper",
    "CellcardMobileScraper",
    "CellcardWifiScraper",
    "SmartScraper",
    "SmartMobileScraper",
    "SmartWifiScraper",
    "Khmer24Scraper",
    "RealestateKhScraper",
    "RedBusKhScraper",
    "BookMeBusScraper",
    "SokhaHotelScraper",
    "HyattHotelScraper",
    "BayonRestaurantScraper",
    "MefExchangeRateScraper",
    "MocGasolineScraper",
    "AryStorePhoneScraper",
    "GrabUcarePharmacyScraper",
    "GrabLuckySupermarketScraper",
    "GrabChipMongSupermarketScraper",
    "NISCPIScraper",
    "MOC_FUEL_PROVINCE",
    "build_canonical_record",
    "_cffi_get",
    "_cffi_post",
    "_to_float",
    "_strip_html",
    "THROTTLE_DELAY",
]
