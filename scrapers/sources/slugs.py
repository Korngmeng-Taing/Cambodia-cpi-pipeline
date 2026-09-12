"""
scrapers/sources/slugs.py
─────────────────────────
Lightweight registry of all scraper source slugs.
Importing this file incurs zero third-party dependencies (no network,
no curl_cffi, no BeautifulSoup, no DB) allowing Airflow DAG parsing
to execute in milliseconds.
"""

from __future__ import annotations

SCRAPER_SLUGS: list[str] = [
    "aeon",
    "aeon3",
    "arystore",
    "bayonbkk",
    "bookmebus",
    "cellcard",
    "communitypharma",
    "delishop",
    "edc",
    "grab_chipmong",
    "grab_lucky",
    "grab_ucare",
    "hyyathotel",
    "khmer24",
    "khmermoto",
    "l192",
    "mef_fx",
    "metfone",
    "new_gasoline",
    "ppwsa",
    "realestate",
    "redbus",
    "samnangshop",
    "smart",
    "sokhahotel",
]
