> **[!NOTE]**
> **IMPLEMENTATION STATUS (LIVE IN PRODUCTION):** The Gold-layer CPI Calculation Engine is fully operational in production.
> Live components:
> - **Bronze Ingestion:** 23 scrapers (`scrapers/sources/`) extracting atomic prices and official MEF USD/KHR rates into `bronze.raw_prices`.
> - **Silver Processing:** Data cleaning (`int_prices_cleaned.sql`), hybrid vector matching (`pipeline/vector_item_matcher.py`), 12-division COICOP classification (`pipeline/hybrid_embeddings_classifier.py`), and log-linear hedonic quality adjustment (`pipeline/hedonic_regression.py`).
> - **Gold Econometric Layer:** Kimball star schema (`gold.dim_items`, `gold.dim_stores`, `gold.fct_daily_prices`), Jevons micro-indices with 7-day imputation (`gold.fct_elementary_indices`), and Laspeyres 12-division daily aggregates (`gold.fct_cpi_daily`).
> - **Observability & Analytics:** Metabase dashboards (Port 3000) and Power BI models.

**Author:** CPI Engineering & Methodology Team
**Architecture:** Pure Structured Medallion Architecture — PostgreSQL 16 + Airflow + dbt (`D:\CPI PIPELINE`)
**Medallion Layers:** Bronze (`bronze.raw_prices`, `staging.exchange_rates`) ──► Silver (`silver.*` + dbt) ──► Gold (`gold.*`)

---

## 1. Architectural Overview & Ingestion Standards

Every night at 02:00, Airflow orchestrates daily data extraction across **22 Cambodian retail, grocery, telecom, transport, housing, hospitality, fuel, electronics, and dining sources** alongside official USD/KHR exchange rates from the Ministry of Economy & Finance (MEF).

```
                      ┌──────────────────────────────────────────────────────────┐
                      │               23 Daily Scraper DAGs                      │
                      │  (scrape_{source}_dag: 22 sources + MEF FX, fan-out from │
                      │   cpi_master_dag at 02:00 Asia/Phnom_Penh)               │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │              Canonical Normalization Contract            │
                      │  (Schema v1.0, JSON Schema validation, Price bounds, DQ) │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │                 PostgreSQL 16 Bronze                     │
                      │   bronze.raw_prices (Typed atomic product listings)      │
                      │   staging.exchange_rates (Official MEF USD/KHR rate)     │
                      │   staging.raw_scrapes (Batch metadata & audit records)   │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │                Silver Layer (silver_dag)                 │
                      │   pipeline.item_matcher (RapidFuzz / Barcode)            │
                      │   pipeline.gemini_item_reviewer (Auto-Review)            │
                      │   pipeline.gemini_coicop_classifier (AI Memoization)     │
                      │   pipeline.hedonic_regression (Log-linear electronics)   │
                      │   dbt models: int_prices_cleaned, int_coicop_classified, │
                      │   clean_store_prices, classification_queue               │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │                  Gold Layer (gold_dag)                   │
                      │   dbt models: dim_items, dim_stores, fct_daily_prices    │
                      │   Serving views: v_coverage, v_monitor_scraper_daily,    │
                      │   v_monitor_source_health_matrix, v_monitor_price_alerts │
                      │   (Planned: Jevons, Laspeyres, GEKS-Törnqvist, Fisher)   │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │               Serving, Observability & BI                │
                      │   Metabase (Port 3000): Scraper Health Matrix & Alerts   │
                      │   Power BI (Port 5432): Interactive CPI & Inflation BI   │
                      └──────────────────────────────────────────────────────────┘
```

### Core Ingestion Principles:

1. **API-First Architecture**: Wherever available, scrapers query internal REST/GraphQL/PostgREST backends directly, bypassing fragile HTML parsing.
2. **Politeness & Rate Limiting**: Centralized per-domain throttle in `scrapers/base.py` (1 request/sec default, exponential backoff with randomized jitter).
3. **Anti-Bot & TLS Impersonation**: Uses `curl_cffi` browser TLS fingerprint impersonation (`chrome`, `safari`, `edge`) to prevent Cloudflare/Akamai bot challenges.
4. **Dual-Layer Fallback**: If a live 3rd-party vendor site experiences downtime or Cloudflare origin tunnel failure, scrapers automatically fallback to the latest valid historical snapshot or curated baseline tariff matrix with `is_fallback=True` to prevent pipeline interruption.
5. **Zero-Product Quality Gate**: A scrape returning 0 products raises an error before database writes, preventing empty ingestion (`pipeline/bronze_ingestion.py`).
6. **Typed Relational Ingestion**: Every batch is parsed and inserted directly into `bronze.raw_prices` with structured types (Schema-on-Write).

---

## 2. Store-by-Store Scraping Methodology

---

### 1. AEON 1 Phnom Penh (`aeon`)

- **Category / Source Type**: Grocery & Supermarket Retail (`grocery`)
- **COICOP Division**: `01` (Food & Non-Alcoholic Beverages), `02` (Alcohol & Tobacco), `12` (Personal Care / Misc)
- **Target Website**: [https://aeononlineshopping.com](https://aeononlineshopping.com)
- **Best Scraping Method**: **Direct Next.js Proxy REST API**
  - **Endpoint**: `GET /api/proxy/stores/aeon1-aeon-phnom-penh/products?page={p}&limit=100`
  - **Headers**: `x-language: en-gb`, `x-currency: KHR`, standard Chrome User-Agent.
  - **Pagination**: Sequential loop until `page >= totalPages` (approx. 16,000–18,000 products).
  - **Extracted Fields**: Product ID, Title, Sale Price (KHR), Original Price, Barcode, Image URL, Category ID, Discount info, Badges (`dry`, `organic`, `chill`).
  - **Fallback**: Parses `AEON_CSV_FALLBACK_PATH` if live Next.js proxy is unreachable.

---

### 2. AEON 3 Mean Chey (`aeon3`)

- **Category / Source Type**: Department Store / Fashion & Beauty (`fashion`)
- **COICOP Division**: `03` (Clothing & Footwear), `12` (Personal Care / Beauty)
- **Target Website**: [https://aeononlineshopping.com](https://aeononlineshopping.com)
- **Best Scraping Method**: **Direct Next.js Proxy REST API**
  - **Endpoint**: `GET /api/proxy/stores/aeon3-fashion-beauty/products?page={p}&limit=100`
  - **Headers**: Same as AEON 1 (`x-language: en-gb`, `x-currency: KHR`).
  - **Pagination**: Loop over pages with 100 items/page.
  - **Extracted Fields**: Fashion items, cosmetics, footwear, regular & discounted prices in KHR.

---

### 3. Delishop Cambodia (`delishop`)

- **Category / Source Type**: Premium Online Supermarket (`grocery`)
- **COICOP Division**: `01` (Food & Groceries), `02` (Beverages/Alcohol)
- **Target Website**: [https://delishop.asia](https://delishop.asia)
- **Best Scraping Method**: **Direct REST API v2**
  - **Endpoint**: `GET https://api.delishop.asia/api/v2/products?page={p}&limit=100`
  - **Headers**: `Origin: https://delishop.asia`, `Referer: https://delishop.asia/`
  - **Pagination**: Automated page increment until returned item array is empty.
  - **Extracted Fields**: `name`, `price` (USD), `original_price`, `barCode` (EAN-13), `brand`, `package_size`, `quantity`, native categories.

---

### 4. L192 Cambodia (`l192`)

- **Category / Source Type**: General Marketplace (`grocery` / retail)
- **COICOP Division**: `01` (Household goods), `03` (Apparel), `05` (Home appliances), `12` (Personal items)
- **Target Website**: [https://www.l192.com](https://www.l192.com)
- **Best Scraping Method**: **Direct GraphQL API**
  - **Endpoint**: `POST https://graph-fs.l192.com/graphql`
  - **Headers**: `Content-Type: application/json`, `x-lang: en`
  - **Query**: Custom GraphQL query selecting `id`, `title`, `price`, `discount_percentage`, `brand_name`, `supplier_name`, `picture_responsive`, `stock_status_label`.
  - **Pagination**: Page offset queries across top marketplace categories.

---

### 5. Community Pharmacy Cambodia (`communitypharma`)

- **Category / Source Type**: Medical & Pharmacy Retail (`pharmacy`)
- **COICOP Division**: `06` (Health & Pharmaceuticals)
- **Target Website**: [https://communitypharma.com.kh/shop](https://communitypharma.com.kh/shop)
- **Best Scraping Method**: **Supabase PostgREST API with Dynamic Bundle Key Resolution**
  - **Endpoint**: `GET https://nceojvynlpcxarizntsk.supabase.co/rest/v1/products?select=*&limit=1000`
  - **Auth**: Public read-only anonymous JWT key (`apikey`, `Authorization: Bearer <key>`).
  - **Dynamic Key Extraction**: Scrapes the homepage `https://communitypharma.com.kh/` and extracts the current bundle (`assets/index-*.js`) to parse the latest JWT token automatically, ensuring zero breakage upon frontend redeployments.
  - **Extracted Fields**: Over 1,100 pharmaceutical items: active ingredients, dosage forms (tablets, syrups, creams), indications, manufacturer brands, barcodes, USD prices.

---

### 6. Khmer Samnang Phone Shop (`samnangshop`)

- **Category / Source Type**: Consumer Electronics & Smartphones (`electronics`)
- **COICOP Division**: `08` (Information & Communication Equipment / Mobile Phones)
- **Target Website**: [https://khmersamnang.com/](https://khmersamnang.com/)
- **Best Scraping Method**: **WooCommerce Store REST API**
  - **Endpoint**: `GET https://khmersamnang.com/wp-json/wc/store/v1/products?per_page=100&page={page}`
  - **Extraction**: Full live catalog across Apple iPhone, Samsung Galaxy, Xiaomi, iPad, Apple Watch, and accessories.
  - **Fields**: Product name, price in USD, full specifications & description, native category hierarchy, permalink URL, image URL.

---

### 7. Cellcard Cambodia Mobile (`cellcard`)

- **Category / Source Type**: Telecommunications & Mobile Data (`telecom`)
- **COICOP Division**: `08` (Information & Communication Services)
- **Target Website**: [https://www.cellcard.com.kh/en/mobile](https://www.cellcard.com.kh/en/mobile)
- **Best Scraping Method**: **Next.js `__NEXT_DATA__` JSON / Card Parser**
  - **Endpoint**: `GET https://www.cellcard.com.kh/en/mobile`
  - **Extraction**: Extracts subscription dial codes (e.g. `*1618*150#`), data allowance (`20 GB`), plan validity (`7 Days`, `30 Days`), and monthly/weekly plan cost in USD.
  - **Coverage**: AO Mobile 5G, Serey, Big Love, Tourist SIMs.

---

### 8. Cellcard Home Internet & Fiber (`cellcard_wifi`)

- **Category / Source Type**: Broadband Internet (`telecom`)
- **COICOP Division**: `08` (Information & Communication Services)
- **Target Website**: [https://www.cellcard.com.kh/en/home-internet/](https://www.cellcard.com.kh/en/home-internet/)
- **Best Scraping Method**: **DOM Card Parsing + Next.js Props**
  - **Extraction**: Speed tiers (e.g. `20 Mbps`, `50 Mbps`, `100 Mbps`), monthly fee in USD, installation/router equipment notes.

---

### 9. Smart Cambodia Mobile (`smart`)

- **Category / Source Type**: Telecommunications & Mobile Data (`telecom`)
- **COICOP Division**: `08` (Information & Communication Services)
- **Target Website**: [https://www.smart.com.kh/plans](https://www.smart.com.kh/plans)
- **Best Scraping Method**: **Multi-URL Card Extraction + Structured Tariff Matrix**
  - **Target Sub-URLs**: `/plans`, `/plans/smart-laor`, `/plans/smart-flexi250`, `/plans/5g-data`, `/plans/traveller-sim`, `/plans/smart-m2m`, `/services/surflikecrazy`.
  - **Extraction**: Dial codes (`*1710*150*1#`), data allowances (GB/MB), validity periods, USD prices.
  - **Fallback**: Pre-seeded structured catalog for Smart Laor!, Flexi, 5G Data, and Traveller SIM plans.

---

### 10. Smart Home Internet & WiFi (`smart_wifi`)

- **Category / Source Type**: Broadband & Wireless Internet (`telecom`)
- **COICOP Division**: `08` (Information & Communication Services)
- **Target Website**: [https://www.smart.com.kh/home-internet](https://www.smart.com.kh/home-internet)
- **Best Scraping Method**: **Multi-URL Card Extraction + Fiber Package Matrix**
  - **Target Sub-URLs**: `/home-internet`, `/Smart-at-home`, `/smart-fiber`, `/5g-at-home`.
  - **Extraction**: Smart @Home, Smart Fiber+, 5G @Home plans, bandwidth speeds (`40Mbps` to `200Mbps`), monthly subscription in USD.

---

### 11. Khmer24 Real Estate (`khmer24`)

- **Category / Source Type**: Residential Housing Rentals (`realestate`)
- **COICOP Division**: `04` (Housing, Water, Electricity, Gas & Other Fuels - Actual Rentals)
- **Target Website**: [https://www.khmer24.com/c-house-for-rent](https://www.khmer24.com/c-house-for-rent)
- **Best Scraping Method**: **Multi-Language Search Scraping (`/en/` and `/km/`)**
  - **Target URLs**: Houses, apartments, condos, villas for rent across Phnom Penh and major provinces.
  - **Extraction**: Monthly rental price (USD), bedroom count, bathroom count, floor/land area ($m^2$), district/location.

---

### 12. Realestate.com.kh (`realestate`)

- **Category / Source Type**: Residential Housing Rentals (`realestate`)
- **COICOP Division**: `04` (Housing Rentals)
- **Target Website**: [https://www.realestate.com.kh/rent/](https://www.realestate.com.kh/rent/)
- **Best Scraping Method**: **Category-Segmented Pagination with Next.js Payload Resolution**
  - **Target Categories**: `/rent/condo/`, `/rent/apartment/`, `/rent/villa/`, `/rent/house/`, `/rent/commercial/`, `/rent/land/`.
  - **Extraction**: Monthly rent (USD), specifications (bedrooms, bathrooms, area $m^2$), geolocation, listing IDs.

---

### 13. redBus Cambodia (`redbus`)

- **Category / Source Type**: Intercity Passenger Transport (`transport`)
- **COICOP Division**: `07` (Transport - Passenger Transport by Road, class `07.3.2`)
- **Target Website**: [https://www.redbus.com.kh/](https://www.redbus.com.kh/)
- **Best Scraping Method**: **Multi-Operator Route & Operator Portal Scraping**
  - **Base Hub**: Phnom Penh (origin hub for all domestic provincial and international bus connections).
  - **Multi-Operator Granularity**: Captures full operator company schedules across each route:
    - *Operators*: Saly VIP, Virak Buntham Express, Larryta Express, Cambolink21 Express, Giant Ibis Transport, Seila Angkor Khmer Express, Capitol Tour and Transport, EVGO Express, VET Airbus Express, Rith Mony Transport, Kumho Samco, Seng Chanthou, Speed Ferry Cambodia, Buva Sea.
    - *Bus / Vehicle Types*: Sleeping Bus 34, Hotel Bus, VIP Van, Luxury Coach, Electric VIP Van, Airbus 45 Seats, Standard Coach, Expressway VIP Minibus, International Coach, Speed Ferry.
  - **Destinations Covered**: Siem Reap, Sihanoukville, Battambang, Kampot, Kep, Poipet, Banteay Meanchey, Mondulkiri, Ratanakiri, Koh Kong, Koh Rong, Koh Rong Sanloem, Kampong Cham, Kampong Thom, Kampong Chhnang, Pursat, Preah Vihear, Kratie, Stung Treng, Takeo, Svay Rieng (Bavet), Prey Veng, Pailin, Bangkok, Ho Chi Minh, Ha Tien, Pakse (53+ active schedule trips).
  - **Extracted Fields**: Route, Operator Company, Bus Type, Ticket Price (USD & converted KHR), Departure Time, Arrival Time, Duration (`expected_hours`), Daily Service status.
  - **Bypass / Resilience**: Uses `curl_cffi` Chrome TLS impersonation to bypass Cloudflare protection and queries live operator fare endpoints dynamically.

---

### 14. BookMeBus Cambodia (`bookmebus`)

- **Category / Source Type**: Intercity Passenger Transport & Travel Booking (`transport`)
- **COICOP Division**: `07` (Transport - Passenger Transport by Road, class `07.3.2`)
- **Target Website**: [https://bookmebus.com/en](https://bookmebus.com/en)
- **Best Scraping Method**: **Live Schedule Search Card Extraction + Multi-Operator Baseline Fallback Matrix**
  - **Base Hub**: Phnom Penh (origin hub ID `1`).
  - **Live Search Querying**: Queries real-time booking date endpoints (`/en/search/bus/phnom-penh/{dest_slug}?on_date={date}`) across 27 Cambodian destinations.
  - **Multi-Operator Extraction**: Parses DOM trip cards for:
    - *Operators*: EVGo Express Cambodia, Seila Angkor Khmer Express, Capitol Tours and Transport, Cambolink21 Express, Saly VIP, Vireak Buntham Express, Larryta Express, Giant Ibis Transport, E-Booking Express, Kim Seng Express, LANA Transportation, Chan Moly Roth Transportation, Ratanak Sambath Express, Phnom Penh Sorya Transport, Seng Chanthou, Kumho Samco, Speed Ferry Cambodia, Buva Sea.
    - *Bus Types*: Electric VIP Van, Sleeping Bus 34, Hotel Bus, Luxury VIP Van, VIP Express, Standard Bus, Airbus 45 Seats, Speed Boat / Ferry.
  - **Per-Destination Fallback Matrix**: If live search for a specific route times out or returns no trips, automatically falls back to curated baseline trips for that specific destination to guarantee 100% route coverage (69+ total trips).
  - **Extracted Fields**: Route, Operator Company, Bus Type, Price (USD), Departure Time, Arrival Time, Duration (`expected_hours`), Booking URL.

---

### 15. Sokha Phnom Penh Hotel (`sokhahotel`)

- **Category / Source Type**: Accommodation Services (`hotel`)
- **COICOP Division**: `11` (Restaurants & Hotels - Accommodation Services)
- **Target Website**: [https://www.sokhahotels.com.kh/phnompenh/](https://www.sokhahotels.com.kh/phnompenh/)
- **Best Scraping Method**: **Hotel Distribution Booking Engine JSON API**
  - **Endpoint**: `GET https://kh-ibe.hopenapi.com/ApiWebDistribution/BookingForm/hotel_info?hotels[0].code=503054`
  - **Extraction**: Room tiers (Deluxe, Premier, Club Suite, Junior Suite, Executive Suite), bed types (King/Twin), room dimensions ($m^2$/sqft), real-time published room rates in USD.

---

### 16. Hyatt Regency Phnom Penh (`hyyathotel`)

- **Category / Source Type**: Accommodation Services (`hotel`)
- **COICOP Division**: `11` (Restaurants & Hotels - Accommodation Services)
- **Target Website**: [https://www.hyatt.com/hyatt-regency/en-US/pnhrp-hyatt-regency-phnom-penh](https://www.hyatt.com/hyatt-regency/en-US/pnhrp-hyatt-regency-phnom-penh)
- **Best Scraping Method**: **Structured Room Specification & Tariff Matrix**
  - **Methodology**: Hyatt web endpoints are protected by enterprise Akamai bot detection. The scraper maintains a verified specification catalog of standard room categories (1 King Bed, 2 Twin Beds, Regency Suite, Executive Suite) with amenities and room dimensions, validated against live booking tariffs.

---

### 17. Bayon Restaurant BKK I (`bayonbkk`)

- **Category / Source Type**: Food & Beverage Service (`restaurant`)
- **COICOP Division**: `11` (Restaurants & Hotels - Catering Services)
- **Target Website**: [https://www.foodpanda.com.kh/en/restaurant/lb0z/bayon-restaurant-bkk-i](https://www.foodpanda.com.kh/en/restaurant/lb0z/bayon-restaurant-bkk-i)
- **Best Scraping Method**: **Embedded Apollo State Extraction (`window.__PROVIDER_PROPS__`)**
  - **Methodology**: Fetches the restaurant page using randomized browser TLS impersonation (`curl_cffi`).
  - **Extraction**: Locates the embedded Apollo Client state within `<script>` tags, extracting `RestaurantMenu`, `RestaurantMenuCategory`, `RestaurantProductData`, and `RestaurantVariationData`.
  - **Yield**: Over 175 complete Khmer & Asian dishes with food names, descriptions, and USD prices without requiring headless browser execution.

---

### 18. Daily USD/KHR Exchange Rate (`scrape_mef_fx_dag`)

- **Category / Source Type**: Macroeconomic Currency Conversion (`fx`)
- **Target Source**: Ministry of Economy and Finance (MEF) / National Bank of Cambodia (NBC)
- **Best Scraping Method**: **Official Central Bank / MEF Rate Fetcher**
  - **Pipeline Integration**: Implemented in `scrapers/sources/mef_fx.py` (MEF FX fetcher) and routed through `pipeline/bronze_ingestion.py::_ingest_fx`. Writes the official daily rate to `staging.exchange_rates` and raw execution records to `staging.raw_scrapes`.
  - **Role in CPI**: USD price observations are converted to KHR (`price_khr`) during the Silver transformation so all elementary price relatives are calculated on a unified national currency basis.

---

### 19. MOC Daily Fuel & LPG Prices (`new_gasoline`)

- **Category / Source Type**: Macroeconomic Fuel & Energy Pricing (`fuel`)
- **COICOP Division**: `07` (Transport — Fuels & Lubricants, class `07.2.2`)
- **Target Sources**: Ministry of Commerce (MOC) portal, Kampuchea Tela Telegram (`t.me/s/telakhmerofficial`), Press Gazettes & Telegram Mirrors
- **Scraping Architecture**: **Direct Official Announcement Cascade (Tela Telegram & Gazette Mirrors)**
  - **Primary — Kampuchea Tela Telegram Feed (`https://t.me/s/telakhmerofficial`)**: Ingests official 10-day gazette announcements published by Cambodia's largest petroleum network. Uses a 4-layer heuristic check (Header + Period + Units + Fuels) to filter marketing and extract:
    - `Super 95 Gasoline` (106): e.g. `5,250 KHR/L`
    - `Regular 92 Gasoline` (107): e.g. `4,400 KHR/L` (MOC official ceiling)
    - `Diesel` (108): e.g. `5,150 KHR/L` (MOC official ceiling)
    - `Petroleum` (109): e.g. `3,950 KHR/L`
    - `LPG Gas` (110): e.g. `2,400 KHR/L` (AutoGas retail price)
  - **Secondary — Official Gazette Media Mirror (Khmer Times)**: Secondary fallback parsing published article body text via regex (`regular gasoline` $\rightarrow$ `4,400`, `diesel` $\rightarrow$ `5,150`).
  - **Tertiary — Public Telegram Channel Preview**: Scrapes `https://t.me/s/freshnewsasia` with Khmer numeral conversion (`០-៩` $\rightarrow$ `0-9`) as third network fallback.
  - **Trading-day resolution**: Fuel & LPG prices apply for 10-day gazette cycles (1st–10th, 11th–20th, 21st–end of month). When the underlying price date differs from the scrape date, the record is flagged `is_fallback=True` with `attrs.source_type='tela_telegram'`.

---

### 20. Ary Store Phone Shop (`arystore`)

- **Category / Source Type**: Consumer Electronics & Smartphones (`electronics`)
- **COICOP Division**: `08` (Information & Communication Equipment / Mobile Phones)
- **Target Website**: [https://arystorephone.com](https://arystorephone.com)
- **Best Scraping Method**: **Public WooCommerce Store REST API (no auth)**
  - **Endpoint**: `GET https://arystorephone.com/wp-json/wc/store/v1/products?per_page=100&page={n}`
  - **Pagination**: Sequential pages of 100 until an empty or short (< page_size) page is returned (~1,352 products, 14 pages).
  - **Extracted Fields**: Name, USD price / regular price / on-sale flag, HTML descriptions (stripped to plain text), images, brands, native categories, tags, SKU, weight, average rating, review count, stock status, and permalink.

---

### 21. Ucare Pharmacy Chroy Changva (`grab_ucare`)

- **Category / Source Type**: Pharmaceuticals, Health & Personal Care (`pharmacy`)
- **COICOP Division**: `06` (Health / Medical Products) & `12` (Personal Care)
- **Target Platform**: [GrabMart Cambodia](https://mart.grab.com/kh/en/merchant/ucare-pharmacy-chroy-changva/10-C7CGV2AFNNEAGJ)
- **Best Scraping Method**: **Next.js Server-Side Embedded JSON (`__NEXT_DATA__`)**
  - **Extraction**: Reads `merchantApi.getMerchant` from preloaded state to extract department item hierarchies (OTC Medicine, Skincare, Vitamins, First Aid, Oral, etc.).
  - **Price Currency**: KHR (`priceInMinorUnit / 100.0`).
  - **Extracted Fields**: Item ID, Name, Price (KHR), Currency, Barcode, SKU, Brand, Category, Image URL, Availability.

---

### 22. Lucky Supermarket Chroy Changva (`grab_lucky`)

- **Category / Source Type**: Supermarket & Groceries (`grocery`)
- **COICOP Division**: `01` (Food & Non-Alcoholic Beverages), `02` (Alcohol & Tobacco), `05` (Household Maintenance), `12` (Personal Care)
- **Target Platform**: [GrabMart Cambodia](https://mart.grab.com/kh/en/merchant/lucky-supermarket-chroy-changva/10-C7CGVZEFJ76BJN)
- **Best Scraping Method**: **Next.js Server-Side Embedded JSON (`__NEXT_DATA__`)**
  - **Extraction**: Reads `merchantApi.getMerchant` covering 46 supermarket departments (Fresh Produce, Meat & Seafood, Dairy, Bakery, Breakfast, Canned Goods, Beverages, Cooking Essentials, etc.).
  - **Price Currency**: KHR (`priceInMinorUnit / 100.0`).
  - **Extracted Fields**: Item ID, Name, Price (KHR), Currency, Barcode, SKU, Department, Image URL.

---

### 23. Chip Mong Supermarket Eden (`grab_chipmong`)

- **Category / Source Type**: Supermarket & Groceries (`grocery`)
- **COICOP Division**: `01` (Food & Non-Alcoholic Beverages), `02` (Alcohol), `05` (Household Maintenance)
- **Target Platform**: [GrabMart Cambodia](https://mart.grab.com/kh/en/merchant/chip-mong-supermarket-eden/10-C7CGVPK3TJ3AEX)
- **Best Scraping Method**: **Next.js Server-Side Embedded JSON (`__NEXT_DATA__`)**
  - **Extraction**: Reads `merchantApi.getMerchant` covering 27 grocery departments with query-aware exponential retry.
  - **Price Currency**: KHR (`priceInMinorUnit / 100.0`).
  - **Extracted Fields**: Item ID, Name, Price (KHR), Currency, Barcode, SKU, Department, Image URL.

---

## 3. Canonical Bronze Contract (Schema v1.0)

Every scraper normalizes its output via `pipeline.canonical.normalize_record()` to strictly conform to the following schema before storage in `bronze.raw_prices`:

```json
{
  "scrape_date": "2026-08-17",
  "source_slug": "delishop",
  "source_type": "grocery",
  "store": "Delishop Cambodia",
  "currency": "USD",
  "cpi_eligible": true,
  "item_id": "18492",
  "barcode": "8850188800123",
  "name": "Angkor Beer Can 330ml",
  "category_native": "Beers & Ciders",
  "price": 0.85,
  "original_price": 0.95,
  "discount_pct": 10.53,
  "on_promo": true,
  "promo": { "type": "discount", "value": 0.1, "start": null, "end": null },
  "badges": ["chilled"],
  "rating": 4.8,
  "flag_a": null,
  "flag_b": null,
  "image_url": "https://delishop.asia/img/p/18492.jpg",
  "url": "https://delishop.asia/product/angkor-beer-330ml",
  "is_fallback": false,
  "source": "scrape",
  "scraped_at": "2026-08-17T03:00:15Z",
  "attrs": { "volume_ml": 330 },
  "brand": "Angkor",
  "quantity": "330ml",
  "package_size": "330ml",
  "unit": "CAN",
  "is_out_of_stock": false
}
```

---

## 4. Maintenance & Operational Procedures

### Testing Individual Scrapers via CLI

```bash
# Run any scraper directly from the repository root (19 sources + MEF FX):
python -c "
import sys, logging
from scrapers.sources import SCRAPER_REGISTRY
from pipeline.bronze_ingestion import ingest_source_bronze

log = logging.getLogger('scraper_test')
print('Available sources:', list(SCRAPER_REGISTRY.keys()))
result = ingest_source_bronze('delishop', '2026-08-17')
print(f'Ingested {result[\"records\"]} products for {result[\"source_slug\"]}.')
"
```

### Running Test Suite

```bash
pytest tests/ -v
# dbt data quality gates:
docker compose exec airflow-scheduler dbt test --project-dir /opt/airflow/dbt
```

### Triggering Full Pipeline in Airflow

```bash
docker exec airflow-scheduler airflow dags trigger cpi_master_dag
# (fans out to 23 scraper DAGs → silver_dag → gold_dag)
```

---

## 5. Regulated Utility Tariffs — Fixed-Price Sources

Electricity and water are regulated state tariffs (COICOP Division `04` — *Housing, Water, Electricity, Gas & Other Fuels*, class `04.5.1` Electricity), set by the Electricity Authority of Cambodia (EAC) and Phnom Penh Water Supply Authority (PPWSA). These prices are stable year-round and are held in a **curated seed** rather than scraped: **`silver.utility_tariffs`** (`dbt/seeds/utility_tariffs.csv`, registered in `dbt/dbt_project.yml`, guarded by `dbt/tests/test_utility_tariffs.sql`).

| Field | Value |
|---|---|
| Electricity (representative fixed price) | **610 Riel/kWh** (EDC Phnom Penh residential, tier 51–200 kWh) |
| Water (representative fixed price) | **960 Riel/m³** (PPWSA domestic, tier 16–25 m³) |
| Currency basis | KHR (official fixed-price basis; USD/EUR-denominated items converted via MEF FX) |
| Effective | 2020-01-01 → present (current regulated tariff regime) |

### 5.1 Electricity — EDC / EAC Sources

| # | Source | URL | What it confirms |
|---|---|---|---|
| 1 | GlobalPetrolPrices (Dec 2025), citing EAC | https://www.globalpetrolprices.com/Cambodia/electricity_prices/ | Residential electricity = **KHR 610 / kWh = USD 0.152** (incl. taxes/fees); next EAC update Jun 2026 |
| 2 | EAC via Open Development Cambodia — Low Voltage tariff | https://opendevelopmentcambodia.net/ (EAC Power Sector Report) | EDC Phnom Penh/Kandal low-voltage = 820 Riel/kWh (2015 historical baseline) |
| 3 | Khmer Times (Apr 2022), quoting EAC chairman | https://www.khmertimeskh.com/ | Current 4-tier household tariff: **380 / 480 / 610 / 730 Riel/kWh** |
| 4 | Energy Tracker Asia (Mar 2024) | https://energytracker.asia/electricity-in-cambodia/ | Cambodia electricity tops USD 0.137/kWh — among region's highest |
| 5 | StatRanker / Statista (2025–2026) | https://www.globalpetrolprices.com/ (benchmark feed) | Household electricity benchmark derived from GlobalPetrolPrices data |

### 5.2 Water — PPWSA Sources

| # | Source | URL | What it confirms |
|---|---|---|---|
| 6 | PPWSA official site — House Connection / tariff | https://www.ppwsa.com.kh/en/index.php?page=house-connection | "2020 to Present" domestic tiers: **400 / 720 / 960 / 1,250 / 1,900 / 2,200 Riel/m³** (authoritative) |
| 7 | Open Development Cambodia — PPWSA water consumption tariff | https://opendevelopmentcambodia.net/profiles/access-to-public-service/ppwsa-water-consumption-tariff | Tier schedule + Decision No. 169 (16 Aug 2019) on 2020 price adjustment |
| 8 | PPWSA Annual Report 2023 (English PDF) | https://www.ppwsa.com.kh/Administration/downloads/finance/PPWSA_Annual_Report_2023(EN).pdf | Official tariff history & consumption statistics |
| 9 | PPWSA 2025 budget disclosure | https://www.ppwsa.com.kh/ | 253.64M m³ sales vs KHR 430.7bn revenue → blended average ≈ **1,698 Riel/m³** (all customer classes) |
| 10 | JICA survey (historical) | (JICA Cambodia urban water survey) | 2016 average tariff ≈ 1,029 KHR/m³ (trend reference only) |

### 5.3 Recommended Fixed Prices (CPI basket)

- **Electricity = 610 Riel/kWh** — modal EDC residential band (51–200 kWh), corroborated independently by GlobalPetrolPrices (Dec 2025) citing EAC.
- **Water = 960 Riel/m³** — PPWSA domestic band 16–25 m³ (typical household). Effective average for a ~20 m³ household ≈ **670 Riel/m³**; PPWSA blended average across all customers ≈ **1,700 Riel/m³**.

Load with: `dbt seed --select utility_tariffs` then `dbt test --select test_utility_tariffs`.
