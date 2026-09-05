from __future__ import annotations

import re
import time
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
    build_canonical_record,
    log,
)


# 15. BookMeBus Cambodia — Intercity Bus & Transport (Phnom Penh Base)
# ═══════════════════════════════════════════════════════════════════════════
BOOKMEBUS_BASE_URL = "https://bookmebus.com/en"
BOOKMEBUS_DESTINATIONS_API = (
    "https://bookmebus.com/en/locations/get_destinations?origin_id=1"
)

BOOKMEBUS_BASELINE_ROUTES = [
    # Siem Reap
    {
        "id": "bmb_pnh_rep_evgo_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "EVGo Express Cambodia",
        "bus_type": "Electric VIP Van",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 8.00,
    },
    {
        "id": "bmb_pnh_rep_rithmony_bus",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Rith Mony Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 8.50,
    },
    {
        "id": "bmb_pnh_rep_capitol_bus",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Capitol Tours",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 9.50,
    },
    {
        "id": "bmb_pnh_rep_seila_vip",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Express",
        "dep": "04:30 PM",
        "arr": "10:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 10.50,
    },
    {
        "id": "bmb_pnh_rep_ebooking_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "E-Booking Express",
        "bus_type": "VIP Van",
        "dep": "04:30 PM",
        "arr": "09:45 PM",
        "dur": "5 hrs 15 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_rep_cambolink_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "04:05 PM",
        "arr": "10:05 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.25,
    },
    {
        "id": "bmb_pnh_rep_vet_airbus",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "VET Airbus Express",
        "bus_type": "Airbus 45 Seats",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.00,
    },
    {
        "id": "bmb_pnh_rep_saly_sleep",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Saly VIP",
        "bus_type": "Sleeping Bus 34",
        "dep": "11:30 PM",
        "arr": "05:00 AM",
        "dur": "5 hrs 30 mins",
        "price": 14.45,
    },
    {
        "id": "bmb_pnh_rep_larryta_van",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Larryta Express",
        "bus_type": "Luxury VIP Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.50,
    },
    {
        "id": "bmb_pnh_rep_virak_hotel",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:00 AM",
        "dur": "6 hrs 30 mins",
        "price": 15.00,
    },
    {
        "id": "bmb_pnh_rep_giant_coach",
        "dest": "Siem Reap",
        "slug": "siem-reap",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury Coach",
        "dep": "08:45 AM",
        "arr": "02:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
    },
    # Sihanoukville
    {
        "id": "bmb_pnh_kos_capitol_bus",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
    },
    {
        "id": "bmb_pnh_kos_bayon_van",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Bayon VIP Express",
        "bus_type": "Express Van",
        "dep": "09:30 AM",
        "arr": "12:30 PM",
        "dur": "3 hrs 00 mins",
        "price": 11.50,
    },
    {
        "id": "bmb_pnh_kos_cambolink_van",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van Expressway",
        "dep": "09:00 AM",
        "arr": "12:00 PM",
        "dur": "3 hrs 00 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_kos_vet_coach",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "VET Airbus Express",
        "bus_type": "Expressway Coach",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 12.50,
    },
    {
        "id": "bmb_pnh_kos_larryta",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Larryta Express",
        "bus_type": "VIP Van Expressway",
        "dep": "08:00 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 00 mins",
        "price": 13.00,
    },
    {
        "id": "bmb_pnh_kos_giant_van",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus Expressway",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 14.00,
    },
    {
        "id": "bmb_pnh_kos_virak_bus",
        "dest": "Sihanoukville",
        "slug": "sihanoukville",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper Bus",
        "dep": "11:30 PM",
        "arr": "03:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 15.00,
    },
    # Battambang
    {
        "id": "bmb_pnh_bbg_rithmony",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Rith Mony Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 7.50,
    },
    {
        "id": "bmb_pnh_bbg_capitol",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 30 mins",
        "price": 9.00,
    },
    {
        "id": "bmb_pnh_bbg_saly_vip",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Saly VIP",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 00 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_bbg_seila",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Seila Angkor Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "12:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_bbg_cambolink",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "08:30 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.50,
    },
    {
        "id": "bmb_pnh_bbg_virak_night",
        "dest": "Battambang",
        "slug": "battambang",
        "operator": "Virak Buntham Express",
        "bus_type": "Night Sleeper",
        "dep": "11:00 PM",
        "arr": "04:30 AM",
        "dur": "5 hrs 30 mins",
        "price": 13.00,
    },
    # Kampot & Kep
    {
        "id": "bmb_pnh_kpt_capitol_bus",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Capitol Tours",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "11:00 AM",
        "dur": "4 hrs 00 mins",
        "price": 7.00,
    },
    {
        "id": "bmb_pnh_kpt_champa_van",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Champa Tourist Bus",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 9.50,
    },
    {
        "id": "bmb_pnh_kpt_ekareach",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 10.00,
    },
    {
        "id": "bmb_pnh_kpt_virak_van",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_kpt_giant_ibis",
        "dest": "Kampot",
        "slug": "kampot",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_kep_ekareach",
        "dest": "Kep",
        "slug": "kep",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
    },
    {
        "id": "bmb_pnh_kep_virak_van",
        "dest": "Kep",
        "slug": "kep",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 11.50,
    },
    # Poipet & Banteay Meanchey
    {
        "id": "bmb_pnh_poi_capitol",
        "dest": "Poi Pet",
        "slug": "poipet",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "03:30 PM",
        "dur": "8 hrs 00 mins",
        "price": 12.00,
    },
    {
        "id": "bmb_pnh_poi_virak",
        "dest": "Poi Pet",
        "slug": "poipet",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:30 AM",
        "dur": "7 hrs 00 mins",
        "price": 16.50,
    },
    {
        "id": "bmb_pnh_bmc_seila",
        "dest": "Banteay Meanchey",
        "slug": "banteay-meanchey",
        "operator": "Seila Angkor Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 13.00,
    },
    {
        "id": "bmb_pnh_bmc_cambolink",
        "dest": "Banteay Meanchey",
        "slug": "banteay-meanchey",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "02:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 14.00,
    },
    # Mondulkiri & Ratanakiri
    {
        "id": "bmb_pnh_mon_rithya",
        "dest": "Mondulkiri",
        "slug": "senmonorom-mondulkiri",
        "operator": "Rithya Mondulkiri Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 15.00,
    },
    {
        "id": "bmb_pnh_mon_virak",
        "dest": "Mondulkiri",
        "slug": "senmonorom-mondulkiri",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
    },
    {
        "id": "bmb_pnh_rat_kimseng",
        "dest": "Ratanakiri",
        "slug": "ratanakiri",
        "operator": "Kim Seng Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "05:00 PM",
        "dur": "10 hrs 00 mins",
        "price": 18.00,
    },
    {
        "id": "bmb_pnh_rat_virak",
        "dest": "Ratanakiri",
        "slug": "ratanakiri",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper",
        "dep": "07:30 PM",
        "arr": "05:30 AM",
        "dur": "10 hrs 00 mins",
        "price": 20.00,
    },
    # Koh Kong & Islands
    {
        "id": "bmb_pnh_kkg_capitol",
        "dest": "Koh Kong",
        "slug": "koh-kong",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "07:00 AM",
        "arr": "02:00 PM",
        "dur": "7 hrs 00 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_kkg_virak",
        "dest": "Koh Kong",
        "slug": "koh-kong",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:45 AM",
        "arr": "01:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.00,
    },
    {
        "id": "bmb_pnh_khr_ferry",
        "dest": "Koh Rong",
        "slug": "koh-rong-via-ferry",
        "operator": "Speed Ferry Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 30 mins",
        "price": 25.00,
    },
    {
        "id": "bmb_pnh_krs_ferry",
        "dest": "Koh Rong Sanloem",
        "slug": "koh-rong-samloem-via-ferry",
        "operator": "Buva Sea Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 25.00,
    },
    # Central & Eastern Provinces
    {
        "id": "bmb_pnh_kcm_sorya",
        "dest": "Kampong Cham",
        "slug": "kampong-cham",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "10:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 6.50,
    },
    {
        "id": "bmb_pnh_kth_capitol",
        "dest": "Kampong Thom",
        "slug": "kampong-thom",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 7.50,
    },
    {
        "id": "bmb_pnh_kch_sorya",
        "dest": "Kampong Chhnang",
        "slug": "kampong-chhnang",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "10:45 AM",
        "dur": "2 hrs 15 mins",
        "price": 5.00,
    },
    {
        "id": "bmb_pnh_pst_capitol",
        "dest": "Pursat",
        "slug": "pursat",
        "operator": "Capitol Tours",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:45 AM",
        "dur": "3 hrs 45 mins",
        "price": 7.00,
    },
    {
        "id": "bmb_pnh_pvh_virak",
        "dest": "Preah Vihear",
        "slug": "preah-vihear-tbeng-meanchey",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "02:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 16.00,
    },
    {
        "id": "bmb_pnh_kra_sorya",
        "dest": "Kratie",
        "slug": "kratie",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 11.00,
    },
    {
        "id": "bmb_pnh_stg_virak",
        "dest": "Stung Treng",
        "slug": "stung-treng",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "08:00 PM",
        "arr": "04:30 AM",
        "dur": "8 hrs 30 mins",
        "price": 18.00,
    },
    {
        "id": "bmb_pnh_tko_sorya",
        "dest": "Takeo",
        "slug": "takeo",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "09:00 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 00 mins",
        "price": 4.50,
    },
    {
        "id": "bmb_pnh_svr_virak",
        "dest": "Svay Rieng (Bavet)",
        "slug": "svay-rieng-bavet",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 9.00,
    },
    {
        "id": "bmb_pnh_pvn_sorya",
        "dest": "Prey Veng",
        "slug": "prey-veng",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 30 mins",
        "price": 5.50,
    },
    {
        "id": "bmb_pnh_pln_virak",
        "dest": "Pailin",
        "slug": "pailin",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "03:00 PM",
        "dur": "7 hrs 00 mins",
        "price": 15.00,
    },
    # International Connections
    {
        "id": "bmb_pnh_bkk_virak_coach",
        "dest": "Bangkok",
        "slug": "bangkok",
        "operator": "Virak Buntham Express",
        "bus_type": "International Coach",
        "dep": "07:30 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 30 mins",
        "price": 20.00,
    },
    {
        "id": "bmb_pnh_bkk_giant_coach",
        "dest": "Bangkok",
        "slug": "bangkok",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 00 mins",
        "price": 35.00,
    },
    {
        "id": "bmb_pnh_sgn_kumho_coach",
        "dest": "Ho Chi Minh",
        "slug": "ho-chi-minh",
        "operator": "Kumho Samco Express",
        "bus_type": "VIP Sleeper Coach",
        "dep": "06:30 AM",
        "arr": "01:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 20.00,
    },
    {
        "id": "bmb_pnh_sgn_giant_coach",
        "dest": "Ho Chi Minh",
        "slug": "ho-chi-minh",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 27.00,
    },
    {
        "id": "bmb_pnh_htn_virak_van",
        "dest": "Ha Tien",
        "slug": "ha-tien",
        "operator": "Virak Buntham Express",
        "bus_type": "Border Express Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 21.00,
    },
    {
        "id": "bmb_pnh_pks_chanthou_bus",
        "dest": "Pakse",
        "slug": "pakse",
        "operator": "Seng Chanthou Transport",
        "bus_type": "International Bus",
        "dep": "07:00 AM",
        "arr": "04:30 PM",
        "dur": "9 hrs 30 mins",
        "price": 37.00,
    },
]


class BookMeBusScraper(BaseScraper):
    """
    BookMeBus Cambodia Scraper (https://bookmebus.com/en).
    Extracts multi-operator intercity bus & transport schedules originating from Phnom Penh
    to all Cambodian provinces and cities.
    Captures: route, bus company/operator (Saly VIP, Virak Buntham, Cambolink 21, Larryta, Giant Ibis, etc.),
              bus type, ticket price, departure time, arrival time, and duration.
    """

    def __init__(self):
        super().__init__(store_slug="bookmebus", source_type="transport")

    def _fetch_destinations(self) -> list[dict[str, Any]]:
        """Fetch active Cambodian destination routes from Phnom Penh."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            resp = _cffi_get(BOOKMEBUS_DESTINATIONS_API, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                cambodia_dests = []
                for d in data:
                    attrs = d.get("attributes", {})
                    dest = attrs.get("destination", {})
                    if (
                        dest.get("country_code") == "KH"
                        and dest.get("slug") != "phnom-penh"
                    ):
                        cambodia_dests.append(
                            {
                                "name": dest.get("name"),
                                "slug": dest.get("slug"),
                                "duration_sec": attrs.get("duration"),
                            }
                        )
                if cambodia_dests:
                    return cambodia_dests
        except Exception as exc:
            log.warning(
                "Failed to fetch BookMeBus destinations API (%s), using default route list",
                exc,
            )

        # Comprehensive fallback destination list
        return [
            {"name": "Siem Reap", "slug": "siem-reap"},
            {"name": "Sihanoukville", "slug": "sihanoukville"},
            {"name": "Battambang", "slug": "battambang"},
            {"name": "Kampot", "slug": "kampot"},
            {"name": "Kep", "slug": "kep"},
            {"name": "Poi Pet", "slug": "poipet"},
            {"name": "Mondulkiri", "slug": "senmonorom-mondulkiri"},
            {"name": "Ratanakiri", "slug": "ratanakiri"},
            {"name": "Koh Kong", "slug": "koh-kong"},
            {"name": "Kampong Cham", "slug": "kampong-cham"},
            {"name": "Kampong Thom", "slug": "kampong-thom"},
            {"name": "Banteay Meanchey", "slug": "banteay-meanchey"},
            {"name": "Preah Vihear", "slug": "preah-vihear-tbeng-meanchey"},
            {"name": "Kratie", "slug": "kratie"},
            {"name": "Stung Treng", "slug": "stung-treng"},
            {"name": "Pursat", "slug": "pursat"},
            {"name": "Kampong Chhnang", "slug": "kampong-chhnang"},
            {"name": "Takeo", "slug": "takeo"},
            {"name": "Svay Rieng (Bavet)", "slug": "svay-rieng-bavet"},
            {"name": "Prey Veng", "slug": "prey-veng"},
            {"name": "Pailin", "slug": "pailin"},
            {"name": "Koh Rong", "slug": "koh-rong-via-ferry"},
            {"name": "Koh Rong Sanloem", "slug": "koh-rong-samloem-via-ferry"},
            {"name": "Bangkok", "slug": "bangkok"},
            {"name": "Ho Chi Minh", "slug": "ho-chi-minh"},
            {"name": "Ha Tien", "slug": "ha-tien"},
            {"name": "Pakse", "slug": "pakse"},
        ]

    def _parse_search_html(
        self, html_text: str, origin_name: str, dest_name: str
    ) -> list[dict[str, Any]]:
        """Parse live schedule cards from BookMeBus search HTML."""
        if not HAS_BS4:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        candidate_divs = soup.find_all(
            lambda tag: tag.name == "div"
            and re.search(r"USD\s*[\d\.]+", tag.get_text())
            and re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM)", tag.get_text())
        )

        seen = set()
        trips = []

        for div in candidate_divs:
            txt = div.get_text(" ", strip=True)
            times = re.findall(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", txt)
            prices = re.findall(r"USD\s*([\d\.]+)", txt)
            duration_m = re.search(
                r"(\d+H\s*\d*|\d+h\s*\d*m?|\d+\s*hours?)", txt, re.IGNORECASE
            )

            if len(times) >= 2 and prices:
                dep_time = times[0]
                arr_time = times[1]
                try:
                    price = float(prices[0])
                except ValueError:
                    continue

                if dep_time == "11:59 AM" and arr_time == "5:59 PM":
                    continue

                duration = (
                    duration_m.group(1).strip() if duration_m else "6 hrs 00 mins"
                )

                img = div.find("img", alt=True)
                operator = img.get("alt").strip() if img and img.get("alt") else ""

                type_m = re.search(
                    r"(Sleeping Bus\s*\d*|VIP\s*Van|Minivan\s*\d*|Luxury\s*Bus|Express\s*Bus|Hotel\s*Bus|Private\s*Taxi|Sedan|SUV|VIP\s*Bus|Standard\s*Bus|Transit\s*Van|Ferry|Speed\s*Boat|Express\s*Boat)",
                    txt,
                    re.IGNORECASE,
                )
                bus_type = type_m.group(1).strip() if type_m else "VIP Express"

                if not operator or operator.lower() in [
                    "home",
                    "loader",
                    "logo",
                    "thumbnail",
                ]:
                    lines = [
                        item_line.strip()
                        for item_line in div.get_text("\n").split("\n")
                        if item_line.strip()
                    ]
                    for line_text in lines:
                        if (
                            not re.search(
                                r"\d{1,2}:\d{2}|Departure|Arrival|USD|Reviews|Info|Left|Seat|Boarding|Drop-off",
                                line_text,
                                re.IGNORECASE,
                            )
                            and len(line_text) < 40
                            and not line_text.isdigit()
                        ):
                            operator = line_text
                            break

                operator = operator or "BookMeBus Partner"

                key = (operator, dep_time, arr_time, price)
                if key not in seen:
                    seen.add(key)
                    trips.append(
                        {
                            "operator": operator,
                            "bus_type": bus_type,
                            "departure_time": dep_time,
                            "arrival_time": arr_time,
                            "expected_hours": duration,
                            "price_usd": price,
                        }
                    )

        return trips

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        # Anchor BOTH the record date and the queried travel date to
        # scrape_date (+2 days so schedules are bookable). Previously the
        # travel date came from wall-clock today(), so backfilled runs fetched
        # current prices while labelling them with the historical scrape_date.
        ds_date = (
            pendulum.parse(str(scrape_date)).date()
            if scrape_date
            else pendulum.today("Asia/Phnom_Penh").date()
        )
        ds = ds_date.format("YYYY-MM-DD")
        target_date = ds_date.add(days=2).format("DD-MM-YYYY")

        html_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        records: list[dict[str, Any]] = []
        destinations = self._fetch_destinations()
        recorded_dest_slugs = set()

        for dest_info in destinations:
            dest_name = dest_info["name"]
            slug = dest_info["slug"]
            url = f"https://bookmebus.com/en/search/bus/phnom-penh/{slug}?on_date={target_date}"

            try:
                resp = _cffi_get(url, headers=html_headers, timeout=8)
                if resp.status_code == 200:
                    trips = self._parse_search_html(resp.text, "Phnom Penh", dest_name)
                    if trips:
                        recorded_dest_slugs.add(slug)
                        for idx, trip in enumerate(trips):
                            operator_clean = trip["operator"]
                            bus_type_clean = trip["bus_type"]
                            item_id = f"bmb_{slug}_{re.sub(r'[^a-zA-Z0-9]', '_', operator_clean).lower()}_{idx}"

                            records.append(
                                build_canonical_record(
                                    source_slug="bookmebus",
                                    source_type="transport",
                                    store_name="BookMeBus Cambodia",
                                    item_id=item_id,
                                    name=f"Bus Ticket: Phnom Penh - {dest_name} ({operator_clean} {bus_type_clean})",
                                    price=trip["price_usd"],
                                    currency="USD",
                                    category_native="Intercity Bus > Passenger Transport by Road",
                                    url=url,
                                    scrape_date=ds,
                                    is_fallback=False,
                                    attrs={
                                        "origin": "Phnom Penh",
                                        "destination": dest_name,
                                        "operator": operator_clean,
                                        "bus_type": bus_type_clean,
                                        "departure_time": trip["departure_time"],
                                        "arrival_time": trip["arrival_time"],
                                        "expected_hours": trip["expected_hours"],
                                        "booking_url": url,
                                    },
                                )
                            )
            except Exception as exc:
                log.debug("BookMeBus route %s live query notice (%s)", slug, exc)

            time.sleep(0.1)

        # For any destination not returned by live search, populate the operator baseline routes
        for route in BOOKMEBUS_BASELINE_ROUTES:
            if route["slug"] not in recorded_dest_slugs:
                records.append(
                    build_canonical_record(
                        source_slug="bookmebus",
                        source_type="transport",
                        store_name="BookMeBus Cambodia",
                        item_id=route["id"],
                        name=f"Bus Ticket: Phnom Penh - {route['dest']} ({route['operator']} {route['bus_type']})",
                        price=route["price"],
                        currency="USD",
                        category_native="Intercity Bus > Passenger Transport by Road",
                        url=f"https://bookmebus.com/en/search/bus/phnom-penh/{route['slug']}?on_date={target_date}",
                        scrape_date=ds,
                        is_fallback=True,
                        attrs={
                            "origin": "Phnom Penh",
                            "destination": route["dest"],
                            "operator": route["operator"],
                            "bus_type": route["bus_type"],
                            "departure_time": route["dep"],
                            "arrival_time": route["arr"],
                            "expected_hours": route["dur"],
                        },
                    )
                )

        return records
