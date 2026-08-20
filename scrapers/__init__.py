"""
scrapers
────────
Web and API scrapers for retail product and price ingestion (Bronze layer).
"""

from scrapers.base import BaseScraper
from scrapers.sources import SCRAPER_REGISTRY

__all__ = ["BaseScraper", "SCRAPER_REGISTRY"]
