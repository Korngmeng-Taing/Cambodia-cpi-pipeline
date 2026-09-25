# Cambodia Consumer Price Index Weights (CEIC / NIS Benchmark)

* **Source Platform:** [CEIC Data](https://www.ceicdata.com/en/cambodia/consumer-price-index-phnom-penh-octdec-2006100-weights/consumer-price-index-weights-phnom-penh-pnp-all-items)
* **National Authority:** National Institute of Statistics (NIS), Ministry of Planning, Cambodia
* **Survey Baseline:** Cambodia Socio-Economic Survey (CSES) 2004 Household Expenditure
* **Index Reference Period:** October – December 2006 = 100
* **Data File:** [`data/ceic_cpi_weights_phnom_penh_2006.csv`](file:///D:/CPI%20PIPELINE/data/ceic_cpi_weights_phnom_penh_2006.csv)

---

## 1. Structure of the CEIC Weights Series

The official CEIC series for Phnom Penh CPI (Oct-Dec 2006=100) is structured into 3 distinct hierarchical levels:

```text
Level 0: All Items (100.000%)
   │
   ▼
Level 1: 12 Major COICOP Divisions (01 through 12)
   │
   ▼
Level 2: COICOP 4-Digit Subclasses / Classes (e.g. 01.1.1, 01.1.2)
```

### Important Statistical Reality Regarding 5 Digits
CEIC Data and NIS Cambodia **do not report expenditure weights at the 5-digit level**. The official series terminates at 4 digits (`Class`). This confirms our pipeline architecture:
* **Tagging & Cleaning:** 5-digit precision is preserved in the Silver layer for semantic clarity.
* **Index Compilation:** Rolled up to the official 4-digit subclasses, where genuine CSES/CEIC weights exist.

---

## 2. 12 Major Division Weights Breakdown

| Code | COICOP Division Description | Khmer Name | Official Weight (%) |
|:---:|:---|:---|:---:|
| **00** | **All Items (Headline CPI)** | **ទំនិញទាំងអស់** | **100.000** |
| 01 | Food and Non-Alcoholic Beverages | ម្ហូបអាហារ និងភេសជ្ជៈមិនមែនជាតិស្រវឹង | 44.775 |
| 02 | Alcoholic Beverages, Tobacco and Narcotics | ភេសជ្ជៈមានជាតិស្រវឹង និងថ្នាំជក់ | 1.625 |
| 03 | Clothing and Footwear | សម្លៀកបំពាក់ និងស្បែកជើង | 3.036 |
| 04 | Housing, Water, Electricity, Gas & Other Fuels | លំនៅឋាន ទឹក អគ្គិសនី ឧស្ម័ន និងឥន្ធនៈ | 17.084 |
| 05 | Furnishings, Household Equipment & Maintenance | គ្រឿងសង្ហារឹម ឧបករណ៍ប្រើប្រាស់ និងការថែទាំ | 2.743 |
| 06 | Health | សុខាភិបាល | 5.141 |
| 07 | Transport | ការដឹកជញ្ជូន | 12.228 |
| 08 | Communication | ការទំនាក់ទំនង | 1.136 |
| 09 | Recreation and Culture | ការកម្សាន្ត និងវប្បធម៌ | 2.912 |
| 10 | Education | ការអប់រំ | 1.174 |
| 11 | Restaurants and Hotels | ភោជនីយដ្ឋាន និងសណ្ឋាគារ | 5.861 |
| 12 | Miscellaneous Goods and Services | ទំនិញ និងសេវាកម្មផ្សេងៗ | 2.285 |

---

## 3. CEIC URL Directory

* **All Items:** [CEIC - All Items](https://www.ceicdata.com/en/cambodia/consumer-price-index-phnom-penh-octdec-2006100-weights/consumer-price-index-weights-phnom-penh-pnp-all-items)
* **Food & Non-Alcoholic Beverages:** [CEIC - Food](https://www.ceicdata.com/en/cambodia/consumer-price-index-phnom-penh-octdec-2006100-weights/consumer-price-index-weights-phnom-penh-pnp-food--nonalcoholic-beverages)
* **Housing & Utilities:** [CEIC - Housing](https://www.ceicdata.com/en/cambodia/consumer-price-index-phnom-penh-octdec-2006100-weights/consumer-price-index-weights-phnom-penh-pnp-housing-water-electricity-gas--other-fuels)
* **Transport:** [CEIC - Transport](https://www.ceicdata.com/en/cambodia/consumer-price-index-phnom-penh-octdec-2006100-weights/consumer-price-index-weights-phnom-penh-pnp-transport)
* **Health:** [CEIC - Health](https://www.ceicdata.com/en/cambodia/consumer-price-index-phnom-penh-octdec-2006100-weights/consumer-price-index-weights-phnom-penh-pnp-health)
* **Restaurants & Hotels:** [CEIC - Restaurants](https://www.ceicdata.com/en/cambodia/consumer-price-index-phnom-penh-octdec-2006100-weights/consumer-price-index-weights-phnom-penh-pnp-restaurants--hotels)
