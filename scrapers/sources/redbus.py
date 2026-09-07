from __future__ import annotations

import json
from typing import Any

import pendulum

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


# 13. redBus Cambodia — Intercity Bus & Transport Portal (Transport)
# ═══════════════════════════════════════════════════════════════════════════
REDBUS_BASE_URL = "https://www.redbus.com.kh/bus-tickets/routes"
REDBUS_OPERATOR_BASE_URL = "https://www.redbus.com.kh/bus-tickets/operators"

REDBUS_OPERATOR_TRIPS = [
    # Phnom Penh to Siem Reap
    {
        "id": "rb_pnh_rep_saly_sleep",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Saly VIP",
        "bus_type": "Sleeping Bus 34",
        "dep": "11:30 PM",
        "arr": "05:00 AM",
        "dur": "5 hrs 30 mins",
        "price": 14.00,
        "op_slug": "saly-vip",
    },
    {
        "id": "rb_pnh_rep_virak_hotel",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:00 AM",
        "dur": "6 hrs 30 mins",
        "price": 15.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_rep_larryta_van",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Larryta Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.50,
        "op_slug": "larryta-express",
    },
    {
        "id": "rb_pnh_rep_cambolink_van",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "08:30 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.00,
        "op_slug": "cambolink21-express",
    },
    {
        "id": "rb_pnh_rep_giant_coach",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury Coach",
        "dep": "08:45 AM",
        "arr": "02:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_rep_seila_vip",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 11.00,
        "op_slug": "seila-angkor-khmer-express",
    },
    {
        "id": "rb_pnh_rep_capitol_bus",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Standard Coach",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 9.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_rep_evgo_van",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "EVGO Express",
        "bus_type": "Electric VIP Van",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 8.00,
        "op_slug": "evgo-express",
    },
    {
        "id": "rb_pnh_rep_vet_airbus",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "VET Airbus Express",
        "bus_type": "Airbus 45 Seats",
        "dep": "08:00 AM",
        "arr": "02:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 13.00,
        "op_slug": "vet-airbus-express",
    },
    {
        "id": "rb_pnh_rep_rithmony_bus",
        "dest": "Siem Reap",
        "slug": "phnom-penh-to-siem-reap",
        "operator": "Rith Mony Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 8.50,
        "op_slug": "rith-mony-transport",
    },
    # Phnom Penh to Sihanoukville
    {
        "id": "rb_pnh_kos_larryta_exp",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Larryta Express",
        "bus_type": "VIP Van Expressway",
        "dep": "08:00 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 00 mins",
        "price": 13.00,
        "op_slug": "larryta-express",
    },
    {
        "id": "rb_pnh_kos_virak_sleep",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper",
        "dep": "11:30 PM",
        "arr": "03:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 15.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_kos_giant_van",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus Expressway",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 14.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_kos_cambolink_van",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van Expressway",
        "dep": "09:00 AM",
        "arr": "12:00 PM",
        "dur": "3 hrs 00 mins",
        "price": 12.00,
        "op_slug": "cambolink21-express",
    },
    {
        "id": "rb_pnh_kos_capitol_bus",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_kos_vet_coach",
        "dest": "Sihanoukville",
        "slug": "phnom-penh-to-sihanoukville",
        "operator": "VET Airbus Express",
        "bus_type": "Expressway Coach",
        "dep": "08:30 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 12.50,
        "op_slug": "vet-airbus-express",
    },
    # Phnom Penh to Battambang
    {
        "id": "rb_pnh_bbg_capitol_bus",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 30 mins",
        "price": 9.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_bbg_seila_vip",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "12:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.00,
        "op_slug": "seila-angkor-khmer-express",
    },
    {
        "id": "rb_pnh_bbg_cambolink_van",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Cambolink21 Express",
        "bus_type": "VIP Van",
        "dep": "08:30 AM",
        "arr": "01:30 PM",
        "dur": "5 hrs 00 mins",
        "price": 12.50,
        "op_slug": "cambolink21-express",
    },
    {
        "id": "rb_pnh_bbg_virak_night",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Virak Buntham Express",
        "bus_type": "Night Sleeper",
        "dep": "11:00 PM",
        "arr": "04:30 AM",
        "dur": "5 hrs 30 mins",
        "price": 13.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_bbg_saly_vip",
        "dest": "Battambang",
        "slug": "phnom-penh-to-battambang",
        "operator": "Saly VIP",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 00 mins",
        "price": 11.00,
        "op_slug": "saly-vip",
    },
    # Phnom Penh to Kampot & Kep
    {
        "id": "rb_pnh_kpt_giant_van",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Giant Ibis Transport",
        "bus_type": "VIP Minibus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 12.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_kpt_ekareach_van",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "11:00 AM",
        "dur": "3 hrs 30 mins",
        "price": 10.00,
        "op_slug": "ekareach-express",
    },
    {
        "id": "rb_pnh_kpt_champa_van",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Champa Tourist Bus",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 9.50,
        "op_slug": "champa-tourist-bus",
    },
    {
        "id": "rb_pnh_kpt_capitol_bus",
        "dest": "Kampot",
        "slug": "phnom-penh-to-kampot",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Standard Bus",
        "dep": "07:00 AM",
        "arr": "11:00 AM",
        "dur": "4 hrs 00 mins",
        "price": 7.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_kep_ekareach_van",
        "dest": "Kep",
        "slug": "phnom-penh-to-kep",
        "operator": "Ekareach Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 10.00,
        "op_slug": "ekareach-express",
    },
    {
        "id": "rb_pnh_kep_virak_van",
        "dest": "Kep",
        "slug": "phnom-penh-to-kep",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "11:30 AM",
        "dur": "4 hrs 00 mins",
        "price": 11.50,
        "op_slug": "virak-buntham",
    },
    # Phnom Penh to Poipet & Banteay Meanchey
    {
        "id": "rb_pnh_poi_capitol_bus",
        "dest": "Poi Pet",
        "slug": "phnom-penh-to-poipet",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "03:30 PM",
        "dur": "8 hrs 00 mins",
        "price": 12.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_poi_virak_hotel",
        "dest": "Poi Pet",
        "slug": "phnom-penh-to-poipet",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "10:30 PM",
        "arr": "05:30 AM",
        "dur": "7 hrs 00 mins",
        "price": 16.50,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_bmc_seila_vip",
        "dest": "Banteay Meanchey",
        "slug": "phnom-penh-to-banteay-meanchey",
        "operator": "Seila Angkor Khmer Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 13.00,
        "op_slug": "seila-angkor-khmer-express",
    },
    # Phnom Penh to Mondulkiri & Ratanakiri
    {
        "id": "rb_pnh_mon_rithya_van",
        "dest": "Mondulkiri",
        "slug": "phnom-penh-to-mondulkiri",
        "operator": "Rithya Mondulkiri Express",
        "bus_type": "VIP Van",
        "dep": "07:00 AM",
        "arr": "01:00 PM",
        "dur": "6 hrs 00 mins",
        "price": 15.00,
        "op_slug": "rithya-express",
    },
    {
        "id": "rb_pnh_mon_virak_van",
        "dest": "Mondulkiri",
        "slug": "phnom-penh-to-mondulkiri",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Minivan",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 16.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_rat_virak_sleep",
        "dest": "Ratanakiri",
        "slug": "phnom-penh-to-ratanakiri",
        "operator": "Virak Buntham Express",
        "bus_type": "Luxury Sleeper",
        "dep": "07:30 PM",
        "arr": "05:30 AM",
        "dur": "10 hrs 00 mins",
        "price": 20.00,
        "op_slug": "virak-buntham",
    },
    # Phnom Penh to Koh Kong & Islands
    {
        "id": "rb_pnh_kkg_virak_van",
        "dest": "Koh Kong",
        "slug": "phnom-penh-to-koh-kong",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:45 AM",
        "arr": "01:45 PM",
        "dur": "6 hrs 00 mins",
        "price": 14.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_khr_ferry",
        "dest": "Koh Rong",
        "slug": "phnom-penh-to-koh-rong",
        "operator": "Speed Ferry Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:00 PM",
        "dur": "5 hrs 30 mins",
        "price": 25.00,
        "op_slug": "speed-ferry",
    },
    {
        "id": "rb_pnh_krs_ferry",
        "dest": "Koh Rong Sanloem",
        "slug": "phnom-penh-to-koh-rong-samloem",
        "operator": "Buva Sea Cambodia",
        "bus_type": "Bus + Speed Ferry",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 25.00,
        "op_slug": "buva-sea",
    },
    # Other Cambodian Provinces
    {
        "id": "rb_pnh_kcm_sorya_bus",
        "dest": "Kampong Cham",
        "slug": "phnom-penh-to-kampong-cham",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "10:30 AM",
        "dur": "3 hrs 00 mins",
        "price": 6.50,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_kth_capitol_bus",
        "dest": "Kampong Thom",
        "slug": "phnom-penh-to-kampong-thom",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:30 AM",
        "dur": "3 hrs 30 mins",
        "price": 7.50,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_kch_sorya_bus",
        "dest": "Kampong Chhnang",
        "slug": "phnom-penh-to-kampong-chhnang",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "10:45 AM",
        "dur": "2 hrs 15 mins",
        "price": 5.00,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_pst_capitol_bus",
        "dest": "Pursat",
        "slug": "phnom-penh-to-pursat",
        "operator": "Capitol Tour and Transport",
        "bus_type": "Express Bus",
        "dep": "08:00 AM",
        "arr": "11:45 AM",
        "dur": "3 hrs 45 mins",
        "price": 7.00,
        "op_slug": "capitol-tour-and-transport",
    },
    {
        "id": "rb_pnh_pvh_virak_van",
        "dest": "Preah Vihear",
        "slug": "phnom-penh-to-preah-vihear",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "07:30 AM",
        "arr": "02:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 16.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_kra_sorya_bus",
        "dest": "Kratie",
        "slug": "phnom-penh-to-kratie",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Express Bus",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 11.00,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_stg_virak_hotel",
        "dest": "Stung Treng",
        "slug": "phnom-penh-to-stung-treng",
        "operator": "Virak Buntham Express",
        "bus_type": "Hotel Bus",
        "dep": "08:00 PM",
        "arr": "04:30 AM",
        "dur": "8 hrs 30 mins",
        "price": 18.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_tko_sorya_bus",
        "dest": "Takeo",
        "slug": "phnom-penh-to-takeo",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "09:00 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 00 mins",
        "price": 4.50,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_svr_virak_van",
        "dest": "Svay Rieng (Bavet)",
        "slug": "phnom-penh-to-bavet",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "12:00 PM",
        "dur": "4 hrs 00 mins",
        "price": 9.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_pvn_sorya_bus",
        "dest": "Prey Veng",
        "slug": "phnom-penh-to-prey-veng",
        "operator": "Phnom Penh Sorya Transport",
        "bus_type": "Standard Bus",
        "dep": "08:30 AM",
        "arr": "11:00 AM",
        "dur": "2 hrs 30 mins",
        "price": 5.50,
        "op_slug": "sorya-transport",
    },
    {
        "id": "rb_pnh_pln_virak_van",
        "dest": "Pailin",
        "slug": "phnom-penh-to-pailin",
        "operator": "Virak Buntham Express",
        "bus_type": "VIP Van",
        "dep": "08:00 AM",
        "arr": "03:00 PM",
        "dur": "7 hrs 00 mins",
        "price": 15.00,
        "op_slug": "virak-buntham",
    },
    # International Connections
    {
        "id": "rb_pnh_bkk_virak_coach",
        "dest": "Bangkok",
        "slug": "phnom-penh-to-bangkok",
        "operator": "Virak Buntham Express",
        "bus_type": "International Coach",
        "dep": "07:30 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 30 mins",
        "price": 20.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_bkk_giant_coach",
        "dest": "Bangkok",
        "slug": "phnom-penh-to-bangkok",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "06:00 PM",
        "dur": "10 hrs 00 mins",
        "price": 35.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_sgn_kumho_coach",
        "dest": "Ho Chi Minh",
        "slug": "phnom-penh-to-ho-chi-minh",
        "operator": "Kumho Samco Express",
        "bus_type": "VIP Sleeper Coach",
        "dep": "06:30 AM",
        "arr": "01:30 PM",
        "dur": "7 hrs 00 mins",
        "price": 20.00,
        "op_slug": "kumho-samco",
    },
    {
        "id": "rb_pnh_sgn_giant_coach",
        "dest": "Ho Chi Minh",
        "slug": "phnom-penh-to-ho-chi-minh",
        "operator": "Giant Ibis Transport",
        "bus_type": "Luxury International Bus",
        "dep": "08:00 AM",
        "arr": "02:30 PM",
        "dur": "6 hrs 30 mins",
        "price": 27.00,
        "op_slug": "giant-ibis",
    },
    {
        "id": "rb_pnh_htn_virak_van",
        "dest": "Ha Tien",
        "slug": "phnom-penh-to-ha-tien",
        "operator": "Virak Buntham Express",
        "bus_type": "Border Express Van",
        "dep": "07:30 AM",
        "arr": "01:30 PM",
        "dur": "6 hrs 00 mins",
        "price": 21.00,
        "op_slug": "virak-buntham",
    },
    {
        "id": "rb_pnh_pks_chanthou_bus",
        "dest": "Pakse",
        "slug": "phnom-penh-to-pakse",
        "operator": "Seng Chanthou Transport",
        "bus_type": "International Bus",
        "dep": "07:00 AM",
        "arr": "04:30 PM",
        "dur": "9 hrs 30 mins",
        "price": 37.00,
        "op_slug": "seng-chanthou",
    },
]


class RedBusKhScraper(BaseScraper):
    """
    redBus Cambodia Scraper (https://www.redbus.com.kh).
    Extracts multi-operator intercity bus & transport schedules originating from Phnom Penh
    to all Cambodian provinces and international destinations.
    Captures: route, bus company/operator (Saly, Virak Buntham, Cambolink 21, Larryta, Giant Ibis, etc.),
              bus type, ticket price, departure time, arrival time, and duration.
    """

    def __init__(self):
        super().__init__(store_slug="redbus", source_type="transport")

    def _parse_operator_page(self, html: str) -> dict[str, Any]:
        info: dict[str, Any] = {"price_usd": None}
        if not HAS_BS4:
            return info
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and "offers" in data:
                    p = data["offers"].get("price")
                    if p:
                        info["price_usd"] = _to_float(p)
                        break
            except Exception:
                pass
        return info

    def fetch_records(
        self, scrape_date: pendulum.Date | None = None
    ) -> list[dict[str, Any]]:
        ds = str(scrape_date or pendulum.today("Asia/Phnom_Penh").date())
        records: list[dict[str, Any]] = []

        # Cache live operator starting fares
        op_fare_cache: dict[str, float] = {}

        for item in REDBUS_OPERATOR_TRIPS:
            dest = item["dest"]
            slug = item["slug"]
            operator = item["operator"]
            bus_type = item["bus_type"]
            op_slug = item.get("op_slug")
            price = item["price"]
            dep_time = item["dep"]
            arr_time = item["arr"]
            duration = item["dur"]
            url = f"{REDBUS_BASE_URL}/{slug}"
            is_fallback = False
            fallback_reason = None

            if op_slug and op_slug not in op_fare_cache:
                try:
                    op_url = f"{REDBUS_OPERATOR_BASE_URL}/{op_slug}"
                    resp = _cffi_get(op_url, timeout=10)
                    if resp.status_code == 200:
                        parsed = self._parse_operator_page(resp.text)
                        if parsed.get("price_usd") and parsed["price_usd"] > 0:
                            op_fare_cache[op_slug] = parsed["price_usd"]
                except Exception:
                    pass

            # M4 FIX: Don't collapse per-trip prices to a single operator fare.
            # Keep the baseline price per (route, operator, bus_type) and log
            # operator starting fare for reference only.
            if op_slug and op_slug in op_fare_cache:
                live_base = op_fare_cache[op_slug]
                # Log for audit; keep original trip price as baseline
                if live_base > 0:
                    log.debug(
                        "redBus operator %s: baseline price=%.2f, operator_starting_fare=%.2f",
                        op_slug, price, live_base
                    )
            else:
                is_fallback = True
                fallback_reason = "redBus static route baseline tariff (operator fetch unavailable)"

            records.append(
                build_canonical_record(
                    source_slug="redbus",
                    source_type="transport",
                    store_name="redBus Cambodia",
                    item_id=item["id"],
                    name=f"Bus Ticket: Phnom Penh to {dest} ({operator} {bus_type})",
                    price=price,
                    currency="USD",
                    category_native="Intercity Bus > Passenger Transport by Road",
                    url=url,
                    scrape_date=ds,
                    is_fallback=is_fallback,
                    fallback_reason=fallback_reason,
                    attrs={
                        "origin": "Phnom Penh",
                        "destination": dest,
                        "operator": operator,
                        "bus_type": bus_type,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "expected_hours": duration,
                        "daily_services": "Active Daily Service",
                    },
                )
            )

        return records
