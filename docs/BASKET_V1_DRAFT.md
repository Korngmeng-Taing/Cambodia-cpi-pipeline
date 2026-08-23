# CPI v1 Basket — Draft (COICOP → Source Mapping)

**Status:** Active Baseline — implemented in Simple Architecture (PostgreSQL 16)  
**Date:** 2026-08-17  
**Grounded in:** actual `category` distribution in `silver.products` + source review.  

**Coverage legend:** ✅ good · 🟡 partial/proxy · 🔴 missing (GAP)

---

## 1. Coverage today (what each source really provides)

| Source | Real categories | COICOP value |
|---|---|---|
| AEON 1 (`aeon`) | Full catalog: rice, meat, fish, fruit, veg, dairy, pantry, beverages (16.9k live items) | 01, 05 |
| AEON 3 (`aeon3`) | Fashion & Beauty, Clothing, Shoes, Accessories (2.4k live items) | 03, 12 |
| Delishop Asia (`delishop`) | Meat, Veg/Fruit, Dairy, Pantry, Beverages, Coffee/Tea, Wine/Spirits, Beauty, Household | 01, 02, 05, 12 |
| L192 (`l192`) | General Retail, Apparel, Kitchen Appliances | 01, 03, 05, 10 |
| Khmer Samnang Shop (`samnangshop`) | Smartphones, Tablets, Tech Accessories (200+ live items) | 08, 09 |
| Ary Store (`arystore`) | Smartphones, Mobile Accessories, Cases, Chargers (1.3k items) | 08, 09, 12 |
| Community Pharma (`communitypharma`) | Rx/OTC meds, Pain Relief, Vitamins, Skincare, First Aid (1.1k items) | 06, 12 |
| Cellcard (`cellcard` & `cellcard_wifi`) | Prepaid mobile data plans, Home fiber internet | 08 |
| Smart (`smart` & `smart_wifi`) | Prepaid mobile data plans, Wireless & fiber home broadband | 08 |
| redBus Cambodia (`redbus`) | Intercity bus routes departing from Phnom Penh to 15 major destinations | 07 |
| BookMeBus (`bookmebus`) | Multi-operator intercity bus & travel booking (27 domestic destinations) | 07 |
| Khmer24 (`khmer24`) | Residential condo, apartment, house rental listings | 04 |
| Realestate.com.kh (`realestate`) | Phnom Penh residential rentals (BKK1, Daun Penh, Tonle Bassac) | 04 |
| Sokha Hotel (`sokhahotel`) | Luxury hotel rooms & suites | 11 |
| Hyatt Regency (`hyyathotel`) | 5-star hotel rooms & suites | 11 |
| Bayon Restaurant (`bayonbkk`) | Authentic Khmer dishes, Bai Cha, Lok Lak, Noodle soups, Beverages | 11 |
| MOC Fuel (`new_gasoline`) | Ministry of Commerce official fuel prices (Regular Gas, Diesel, Petroleum) | 07 |
| MEF FX (`mef_fx`) | Ministry of Economy & Finance official USD/KHR exchange rate | Macro/FX |

---

## 2. V1 Basket by COICOP (Official Weights & Target Items)

### 01 Food & non-alcoholic beverages — *Weight: 44.800%*
| Class | Sample basket items | Source | Status |
|---|---|---|---|
| 01.1.1 Rice & cereals | Packaged rice 5kg (e.g., Angkor Harvest / Jasmine Rice), noodles | AEON, L192, Delishop Pantry | ✅ |
| 01.1.2 Meat | Pork, chicken, beef (per kg / per pack) | Delishop Meat & Poultry, AEON | ✅ |
| 01.1.3 Fish & seafood | Fresh fish, prawns, fish sauce | Delishop Fresh Food, AEON | ✅ |
| 01.1.4 Milk, cheese, eggs | UHT milk 1L, fresh eggs 10pk, cheese, butter | Delishop Dairy, AEON | ✅ |
| 01.1.5 Oils & fats | Cooking oil 1L, olive oil, coconut oil | Delishop Pantry, AEON | ✅ |
| 01.1.6 Fruit | Bananas, mangoes, apples, avocados | Delishop Veggies & Fruits, AEON | ✅ |
| 01.1.7 Vegetables | Tomatoes, cucumbers, cabbages, eggplants | Delishop, AEON | ✅ |
| 01.1.8 Sugar & confectionery | White sugar 1kg, palm sugar, chocolate | Delishop, AEON | ✅ |
| 01.1.9 Food n.e.c. | Fish sauce, soy sauce, instant noodles, salt, curry paste | Delishop, L192, AEON | ✅ |
| 01.2.1 Coffee, tea | Ground coffee, tea bags, instant coffee | Delishop Coffee & Tea, AEON | ✅ |
| 01.2.2 Soft drinks & water | Bottled water 1.5L, soda cans, energy drinks, coconut water | Delishop Beverages, AEON | ✅ |

### 02 Alcohol & tobacco — *Weight: 1.500%*
| Class | Items | Source | Status |
|---|---|---|---|
| 02.1.1 Spirits & beer | Angkor Beer, Cambodia Beer, Heineken, wine, spirits | Delishop Wine & Spirits, AEON | ✅ |
| 02.2.0 Tobacco | Cigarettes, tobacco products | Regulated retail | 🟡 (Proxy / Exception) |

### 03 Clothing & footwear — *Weight: 2.900%*
| Class | Items | Source | Status |
|---|---|---|---|
| 03.1.2 Garments | T-shirts, polo shirts, jeans, dresses, shorts | AEON3 Fashion, L192 | ✅ |
| 03.1.3 Other clothing | Underwear, socks, kidswear | AEON3 | ✅ |
| 03.2.1 Footwear | Running shoes, sneakers, sandals, slippers | AEON3 Footwear | ✅ |

### 04 Housing & utilities — *Weight: 17.100%*
| Class | Items | Source | Status |
|---|---|---|---|
| 04.1.1 Actual rentals | Phnom Penh residential rentals (condos/apartments) | Khmer24, Realestate.com.kh | ✅ |
| 04.4.1 Water supply | PPWSA regulated tariff | `dbt/seeds/utility_tariffs.csv` | ✅ |
| 04.5.1 Electricity | EDC regulated electricity tariff | `dbt/seeds/utility_tariffs.csv` | ✅ |
| 04.5.3 LPG / Gas | LPG cylinder / cooking gas | AEON, Market baseline | ✅ |

### 05 Furnishings & household — *Weight: 3.300%*
| Class | Items | Source | Status |
|---|---|---|---|
| 05.4.0 Cleaning products | Detergent, dishwashing liquid, floor cleaner, bleach | Delishop Pantry, AEON | ✅ |
| 05.6.1 Appliances | Washing machines, refrigerators, microwave ovens | Nika Shop, L192 | ✅ |
| 05.6.2 Small appliances | Electric kettles, rice cookers, blenders, fans | Nika Shop, L192 | ✅ |

### 06 Health — *Weight: 5.600%*
| Class | Items | Source | Status |
|---|---|---|---|
| 06.1.1 Medical products | Paracetamol, Panadol, Redoxon Vitamin C, cough medicine | Community Pharma | ✅ |
| 06.1.2 Medical devices | Thermometers, bandages, antiseptic liniment, test kits | Community Pharma | ✅ |

### 07 Transport — *Weight: 12.200%*
| Class | Items | Source | Status |
|---|---|---|---|
| 07.2.2 Fuels & lubricants | Regular Gasoline, Diesel, Petroleum | Ministry of Commerce (`new_gasoline`) | ✅ |
| 07.3.1 Passenger transport | Intercity express luxury bus, VIP vans, passenger transit | redBus, BookMeBus (Vireak Buntham, Cambolink 21, etc.) | ✅ |

### 08 Communication — *Weight: 3.900%*
| Class | Items | Source | Status |
|---|---|---|---|
| 08.2.0 Telephone equipment | Apple iPhone, Samsung Galaxy, chargers, phone cases | Ary Store, Samnang Shop | ✅ |
| 08.3.0 Telephone services | Cellcard & Smart mobile prepaid bundles, home Wi-Fi broadband | Cellcard, Smart | ✅ |

### 09 Recreation & culture — *Weight: 1.900%*
| Class | Items | Source | Status |
|---|---|---|---|
| 09.1.1 Audio/visual tech | Bluetooth speakers, wireless earbuds, gaming gear | Ary Store, Samnang Shop | ✅ |

### 10 Education — *Weight: 1.500%*
| Class | Items | Source | Status |
|---|---|---|---|
| 10.4.1 School supplies | Notebooks, ballpoint pens, pencil cases, color pencils | L192, AEON | ✅ |

### 11 Restaurants & hotels — *Weight: 3.100%*
| Class | Items | Source | Status |
|---|---|---|---|
| 11.1.1 Restaurants | Bai Cha, Beef Lok Lak, Khmer Noodle Soup, Iced Coffee | Bayon Restaurant BKK I | ✅ |
| 11.2.0 Hotels | Deluxe King Room, Executive Suite, Standard King | Sokha Hotel, Hyatt Regency | ✅ |

### 12 Miscellaneous — *Weight: 2.200%*
| Class | Items | Source | Status |
|---|---|---|---|
| 12.1.1 Personal care | Shampoo, soap, Sunplay sunscreen, Lipice balm, skincare | Community Pharma, AEON3, Delishop | ✅ |

---

## 3. Database Persistence

The basket is selected and processed through:
1. `silver.canonical_items` / `silver.dim_items`: Canonical item identities resolved via EAN/Fuzzy match (`pipeline/item_matcher.py`).
2. `silver.fct_daily_prices`: Conformed daily observations per product/store/date.
3. `gold.base_prices`: Base period geometric mean prices fixed at `base_period = '2026-08'` (dbt model `base_prices.sql`).
4. `gold.category_weights`: Seed table (`dbt/seeds/category_weights.csv`) summing to exactly $100.000\%$, used by `gold.cpi_category_daily` and `gold.cpi_headline_daily`.
