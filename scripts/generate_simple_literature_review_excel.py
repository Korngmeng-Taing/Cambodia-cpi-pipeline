import os
import openpyxl
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

def build_simple_excel(output_paths: list[str]) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    HEADER_FONT = Font(name="Calibri", size=11, bold=True)
    DATA_FONT = Font(name="Calibri", size=11)
    BOLD_DATA_FONT = Font(name="Calibri", size=11, bold=True)

    # TAB 1: Literature Review Matrix
    ws1 = wb.create_sheet(title="Literature Review Matrix")
    ws1.views.sheetView[0].showGridLines = True

    headers1 = [
        "ID", "Pillar / Domain", "Study / Paper Title", "Authors", "Year",
        "Journal / Publisher / Outlet", "Key Methodology & Algorithms",
        "Dataset & Experimental Scope", "Reported Metrics & Empirical Results",
        "Relevance & Mapping to Cambodia CPI Pipeline", "DOI / Citation Link"
    ]
    for col_idx, h in enumerate(headers1, 1):
        c = ws1.cell(row=1, column=col_idx, value=h)
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    matrix_data = [
        [
            "LR-01", "1. High-Frequency Web Scraping",
            "The Billion Prices Project: Using Online Prices for Measurement and Research",
            "Alberto Cavallo & Roberto Rigobon", 2016,
            "Journal of Economic Perspectives (Vol. 30, No. 2, pp. 151-178)",
            "Automated daily web scrapers, Jevons geometric mean, high-frequency online micro price tracking.",
            "Hundreds of multi-channel & pure e-commerce retailers across 22 countries; billions of individual price quotes.",
            "• Pearson correlation >0.98 with official monthly CPI in low-inflation economies (US, Germany, Japan, Brazil).\n• Detected true 20.0% inflation in Argentina (2007–2015) vs 8.0% official reported rate.\n• Detected exchange rate pass-through shocks within 3–14 days (vs 30–60 days official lag).",
            "Provides empirical foundation for daily automated crawling of Cambodian retail e-commerce platforms to eliminate publication lag and capture rapid currency/pass-through shocks.",
            "https://doi.org/10.1257/jep.30.2.151"
        ],
        [
            "LR-02", "1. High-Frequency Web Scraping",
            "Web scraping techniques to collect data on consumer prices and machine learning for product classification",
            "Federico Polidoro, Roberto Giannini, Rosanna Lo Conte, & Silvia Rossetti", 2015,
            "Statistical Journal of the IAOS (Vol. 31, No. 3, pp. 447-461)",
            "Automated scraping architectures, HTML parsing pipelines, text preprocessing, Naive Bayes and Support Vector Machine (SVM) classification.",
            "Italian National Institute of Statistics (ISTAT) empirical scanner & web scraping pilot on consumer electronics and groceries.",
            "• Increased quote sample size by >100x (over two orders of magnitude).\n• Reduced field collection labor costs by >80%.\n• Classification accuracy ranged from 82% to 92.5% across product groups.",
            "Demonstrates the operational viability of substituting manual field enumerator surveys with automated web crawlers in official NSI production pipelines.",
            "https://doi.org/10.3233/SJI-150896"
        ],
        [
            "LR-03", "1. High-Frequency Web Scraping",
            "Practical Guide on the Use of Web Scraping for the Calculation of the Harmonised Index of Consumer Prices (HICP)",
            "Eurostat (Statistical Office of the European Communities)", 2022,
            "Eurostat Methodological Guidelines (Luxembourg)",
            "Crawler rate-limiting, robot.txt compliance, anti-bot mitigation, missing quote handling, longitudinal product ID hashing.",
            "Standardized institutional guidelines across 27 EU National Statistical Institutes.",
            "• Standardized crawler governance, ethical scraping protocols, and data protection.\n• Codified 7-day price carry-forward and geometric imputation rules for missing scraped quotes.",
            "Directly guides the Bronze ingestion layer design, respecting robot policies, retry-backoff algorithms, and raw payload data lake storage.",
            "Eurostat Practical Guide (2022)"
        ],
        [
            "LR-04", "2. NLP & AI in Product Classification",
            "NLP-Enhanced Inflation Measurement Using BERT and Web Scraping",
            "Martin Berki, Vanesa Andicsova, & Milos Oravec", 2025,
            "Frontiers in Artificial Intelligence (Vol. 8, Art. 1543026)",
            "Fine-tuned BERT transformer architecture for multi-class hierarchical text classification into 5-digit COICOP codes.",
            "Over 100,000 scraped e-commerce product titles across retail supermarkets.",
            "• Overall classification accuracy: 94.56%.\n• Weighted precision: 94.07%.\n• Outperformed rule-based regex and TF-IDF baselines on noisy, abbreviated product listings.",
            "Forms the technical foundation for the Silver classification layer, validating transformer embeddings for classifying Cambodian e-commerce items into 12 COICOP divisions.",
            "https://doi.org/10.3389/frai.2025.1543026"
        ],
        [
            "LR-05", "2. NLP & AI in Product Classification",
            "Project Spectrum: Using Generative AI to Enhance Inflation Nowcasting",
            "Bank for International Settlements (BIS), European Central Bank (ECB), & Deutsche Bundesbank", 2024,
            "BIS Innovation Hub Technical Report (Basel, Switzerland)",
            "Large Language Models (LLMs), dense vector embeddings, vector database caching, few-shot prompt engineering.",
            "Billions of scraped price quotes across multi-lingual European retailer catalogs.",
            "• Zero-shot & few-shot LLM reasoning achieved >95% classification precision.\n• Reduced batch processing latency from several days to <3 minutes via vector memoization and cache lookup.",
            "Validates the hybrid Silver layer architecture: using dense vector caching for instant exact match and LLM fallback for ambiguous Khmer/English product descriptions.",
            "https://www.bis.org/about/bisih/topics/ai/spectrum.htm"
        ],
        [
            "LR-06", "2. NLP & AI in Product Classification",
            "Using Machine Learning for Classifying Web-Scraped Data into COICOP",
            "Office for National Statistics (ONS) Data Science Campus", 2020,
            "ONS Methodology Technical Paper (Newport, UK)",
            "FastText & TF-IDF feature extraction, XGBoost classifier, Human-in-the-Loop (HITL) operational confidence thresholding.",
            "UK web-scraped clothing and grocery price panel (millions of quotes).",
            "• Macro F1-score of 87%–91%.\n• Confidence threshold (tau = 0.80) allowed >70% of volume to be fully automated without human intervention while maintaining official statistical quality.",
            "Informs the automated Silver validation pipeline: items with classification confidence >= 0.80 pass automatically, while low-confidence items are flagged for audit.",
            "https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies"
        ],
        [
            "LR-07", "3. Econometric Index Number Theory",
            "Consumer Price Index Manual: Concepts and Methods",
            "IMF, ILO, OECD, Eurostat, UN, & World Bank", 2020,
            "International Monetary Fund (Washington, D.C.)",
            "Axiomatic price index theory, elementary Jevons geometric mean, Carli/Dutot formula bias proofs, missing quote imputation, hedonic quality adjustment.",
            "Global standard methodology for national statistical offices and central banks.",
            "• Proved Jevons geometric mean satisfies time-reversal and transitivity axioms.\n• Proved Carli arithmetic mean suffers from 0.5%–1.5% upward price bounce bias.\n• Mandated Jevons formula as the global best practice for unweighted micro-level aggregation.",
            "Governs the Gold aggregation layer: proves why elementary daily micro-indices in the pipeline must use Jevons geometric averages rather than arithmetic means.",
            "ISBN: 978-1-48435-430-8"
        ],
        [
            "LR-08", "3. Econometric Index Number Theory",
            "Substitution Bias and Scanner Data: Measuring Price Change with Scanner Data",
            "W. Erwin Diewert & Kevin J. Fox", 2020,
            "Journal of Econometrics (Vol. 217, No. 2, pp. 268-284)",
            "Superlative index number formulas (Fisher Ideal, Törnqvist), exact economic index theory, second-order Taylor approximations.",
            "High-frequency barcode scanner transactions across extensive supermarket chains.",
            "• Quantified that standard fixed-basket Laspeyres indices overstate inflation by 0.30%–0.85% per annum due to commodity substitution.\n• Proved superlative indices effectively eliminate substitution bias by capturing shifts toward discounted goods.",
            "Justifies the pipeline's hybrid weighting strategy, combining official CSES fixed weights with dynamic expenditure approximations.",
            "https://doi.org/10.1016/j.jeconom.2019.12.013"
        ],
        [
            "LR-09", "3. Econometric Index Number Theory",
            "A New Methodology for Processing Scanner Data in the Dutch CPI",
            "Antonio G. Chessa", 2016,
            "EURONA — Eurostat Review on National Accounts (Vol. 2016, No. 1, pp. 49-69)",
            "Rolling Multilateral GEKS-Törnqvist index, Quality-Adjusted Unit Value GEKS (QU-GEKS), Movement Splice / Window Splicing (13-month rolling window).",
            "Statistics Netherlands (CBS) comprehensive supermarket scanner data panel.",
            "• Proved multilateral GEKS completely eliminates 'chain drift' (5%–10% cumulative multi-year bias caused by clearance sales and item turnover).\n• Successfully deployed into official Dutch national CPI production.",
            "Provides the theoretical framework for multilateral aggregation in the Gold layer to prevent downward chain drift caused by frequent flash sales on Cambodian e-commerce platforms.",
            "EURONA 2016(1):49-69"
        ],
        [
            "LR-10", "4. ML & Time-Series Nowcasting",
            "Nowcasting Food Inflation with a Massive Amount of Online Prices",
            "Pawel Macias, Damian Stelmasiak, & Karol Szafranek", 2023,
            "International Journal of Forecasting (Vol. 39, No. 2, pp. 809-826)",
            "Mixed-Data Sampling (MIDAS), Autoregressive Distributed Lag (ARDL), daily scraped web panel aggregation for monthly macroeconomic forecasting.",
            "Over 2 million daily food quotes scraped over an 11-year longitudinal panel in Poland.",
            "• 15% to 35% reduction in Root Mean Square Error (RMSE) over standard AR/ARIMA benchmarks when predicting official monthly food CPI.\n• Superior real-time tracking during periods of high economic turbulence and supply shocks.",
            "Directly validates the Gold-to-Platinum nowcasting module: using daily scraped food & beverage sub-indices to nowcast official National Institute of Statistics (NIS) monthly inflation.",
            "https://doi.org/10.1016/j.ijforecast.2022.01.007"
        ],
        [
            "LR-11", "4. ML & Time-Series Nowcasting",
            "Forecasting Inflation in a Data-Rich Environment: The Benefits of Machine Learning Methods",
            "Marcelo C. Medeiros, Gabriel F. R. Vasconcelos, Alvaro Veiga, & Eduardo Zilberman", 2021,
            "Journal of Business & Economic Statistics (Vol. 39, No. 1, pp. 98-119)",
            "Random Forests, Gradient Boosted Regression Trees (GBRT/LightGBM), LASSO, Ridge, Factor Models vs. Phillips Curve and AR benchmarks.",
            "Extensive high-dimensional US macroeconomic dataset (FRED-MD) across 1 to 12-month forecast horizons.",
            "• Tree-based ensembles (Random Forest & GBRT) significantly outperformed all linear econometric benchmarks, reducing MSFE by 10%–25%.\n• Effectively captured non-linear threshold effects and complex macro interactions between commodities, exchange rates, and prices.",
            "Informs the pipeline's multi-horizon forecasting engine, supporting gradient boosting ensembles with commodity and KHR/USD exchange rate regressors.",
            "https://doi.org/10.1080/07350015.2019.1637745"
        ]
    ]

    for row_idx, row_vals in enumerate(matrix_data, 2):
        for col_idx, val in enumerate(row_vals, 1):
            c = ws1.cell(row=row_idx, column=col_idx, value=val)
            c.font = BOLD_DATA_FONT if col_idx in (1, 2) else DATA_FONT
            align_h = "center" if col_idx in (1, 5) else "left"
            c.alignment = Alignment(horizontal=align_h, vertical="top", wrap_text=True)

    col_widths1 = {1: 10, 2: 24, 3: 32, 4: 26, 5: 8, 6: 28, 7: 35, 8: 30, 9: 38, 10: 38, 11: 30}
    for col_idx, w in col_widths1.items():
        ws1.column_dimensions[get_column_letter(col_idx)].width = w

    ws1.auto_filter.ref = f"A1:K{len(matrix_data)+1}"
    ws1.freeze_panes = "C2"

    # TAB 2: Thematic Pillars & Pipeline Architecture
    ws2 = wb.create_sheet(title="Thematic Pillars & Pipeline")
    ws2.views.sheetView[0].showGridLines = True

    headers2 = [
        "Pillar #", "Thematic Research Domain", "Core Academic & Institutional Literature",
        "Key Methodological Principles", "Target Medallion Layer", "Engineering Implementation in Cambodia Pipeline"
    ]
    for col_idx, h in enumerate(headers2, 1):
        c = ws2.cell(row=1, column=col_idx, value=h)
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    pillars_data = [
        [
            "Pillar 1", "High-Frequency Web Scraping & Ingestion",
            "• Cavallo & Rigobon (2016) [BPP]\n• Polidoro et al. (2015) [ISTAT]\n• Eurostat (2022) [HICP Guide]",
            "• Automated daily distributed crawlers.\n• >100x sample size expansion over manual surveys.\n• Detection of macro shocks within 3–14 days.\n• 7-day missing price carry-forward rules.",
            "Bronze Layer (Raw Ingestion)",
            "Daily Playwright/HTTP crawlers targeting 19 Cambodian retail/telecom/transport/hotel sources + MEF FX storing raw JSON/HTML payloads in PostgreSQL bronze.raw_prices and staging.raw_scrapes."
        ],
        [
            "Pillar 2", "NLP & AI in Product Classification",
            "• Berki et al. (2025) [BERT COICOP]\n• BIS / ECB / Bundesbank (2024) [Spectrum]\n• ONS Data Science Campus (2020) [XGBoost]",
            "• Dense transformer embeddings (BERT/RoBERTa).\n• Multi-class hierarchical classification into 12 COICOP divisions.\n• Few-shot LLM reasoning with vector caching.\n• Human-in-the-Loop (HITL) thresholding (tau >= 0.80).",
            "Silver Layer (Enrichment & Standardization)",
            "Hybrid text processing: 15 pure store domain locks + 12-division reference vector cosine matching + Gemini Pro/Flash AI fallback cached in silver.dim_coicop_ai_cache."
        ],
        [
            "Pillar 3", "Econometric Multilateral Index Theory",
            "• IMF/ILO/UN CPI Manual (2020)\n• Diewert & Fox (2020) [Substitution Bias]\n• Chessa (2016) [GEKS / Statistics Netherlands]",
            "• Unweighted Jevons geometric mean satisfies time-reversal & transitivity.\n• Superlative Fisher/Törnqvist eliminates substitution bias (0.3%–0.85%/yr).\n• ILO class-mean imputation advances prices for missing items.",
            "Gold Layer (Aggregations & Analytics)",
            "Two-stage aggregation: Jevons geometric mean for elementary item price ratios (gold.fct_elementary_indices) + Laspeyres fixed-weight division roll-up into headline/core CPI (gold.fct_cpi_daily)."
        ],
        [
            "Pillar 4", "Machine Learning & Macro Nowcasting",
            "• Macias et al. (2023) [MIDAS Nowcasting]\n• Medeiros et al. (2021) [ML Inflation]",
            "• Mixed-Data Sampling (MIDAS) bridging daily online prices to monthly official CPI.\n• 15%–35% RMSE reduction over AR/ARIMA.\n• Gradient Boosted Trees (GBRT/LightGBM) & Random Forests capturing non-linear macro interactions.",
            "Platinum Layer (Nowcasting & Dashboards)",
            "Ensemble forecasting models predicting official National Institute of Statistics (NIS) monthly CPI 20–30 days prior to official publication using daily scraped indexes + exchange rates."
        ]
    ]

    for row_idx, row_vals in enumerate(pillars_data, 2):
        for col_idx, val in enumerate(row_vals, 1):
            c = ws2.cell(row=row_idx, column=col_idx, value=val)
            c.font = BOLD_DATA_FONT if col_idx in (1, 2, 5) else DATA_FONT
            align_h = "center" if col_idx in (1, 5) else "left"
            c.alignment = Alignment(horizontal=align_h, vertical="top", wrap_text=True)

    col_widths2 = {1: 12, 2: 26, 3: 32, 4: 38, 5: 22, 6: 45}
    for col_idx, w in col_widths2.items():
        ws2.column_dimensions[get_column_letter(col_idx)].width = w

    ws2.auto_filter.ref = f"A1:F{len(pillars_data)+1}"
    ws2.freeze_panes = "C2"

    # TAB 3: Methodology & Metrics Benchmark
    ws3 = wb.create_sheet(title="Methodology & Metrics Benchmark")
    ws3.views.sheetView[0].showGridLines = True

    headers3 = [
        "Category", "Algorithm / Formula", "Benchmark / Baseline", "Key Metric / Reported Performance",
        "Advantages", "Limitations / Tradeoffs", "Reference Paper"
    ]
    for col_idx, h in enumerate(headers3, 1):
        c = ws3.cell(row=1, column=col_idx, value=h)
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    bench_data = [
        [
            "NLP Classification", "BERT Transformer (Fine-Tuned)", "TF-IDF + Naive Bayes / SVM",
            "94.56% Accuracy, 94.07% Precision",
            "Deep contextual semantic understanding; handles abbreviations, brands, packaging nuances.",
            "Higher computational footprint; requires GPU or inference optimization.", "Berki et al. (2025)"
        ],
        [
            "NLP Classification", "LLM + Vector Cache (Project Spectrum)", "Handcrafted Regex Rules",
            ">95% Precision, Latency <3 min",
            "Zero-shot/few-shot multi-lingual adaptation (Khmer/English); fast retrieval via caching.",
            "API token costs; potential non-deterministic hallucinations if unconstrained.", "BIS / ECB / Bundesbank (2024)"
        ],
        [
            "NLP Classification", "FastText + XGBoost with HITL (tau=0.80)", "Manual Field Survey Categorization",
            "87%–91% Macro F1, >70% Automated",
            "Lightweight, deterministic confidence scores; high throughput for automated pipelines.",
            "Slightly lower accuracy on rare out-of-vocabulary product items.", "ONS Data Science Campus (2020)"
        ],
        [
            "Index Calculation", "Jevons Geometric Mean", "Carli Arithmetic Mean / Dutot Ratio",
            "Eliminates 0.5%–1.5% Upward Bias",
            "Axiomatically sound (satisfies time-reversal & transitivity); standard for unweighted micro prices.",
            "Cannot handle zero prices without imputation or shift constants.", "IMF CPI Manual (2020)"
        ],
        [
            "Index Calculation", "Superlative Indices (Fisher / Törnqvist)", "Fixed-base Laspeyres Index",
            "Removes 0.3%–0.85%/yr Substitution Bias",
            "Exact second-order approximation to true cost of living; accommodates consumer substitution.",
            "Requires simultaneous real-time quantity/expenditure weights.", "Diewert & Fox (2020)"
        ],
        [
            "Index Calculation", "Rolling Multilateral GEKS (Movement Splice)", "Direct Bilateral Chained Indices",
            "Eliminates 5%–10% Cumulative Chain Drift",
            "Prevents multi-year downward/upward drift caused by clearance sales and item turnover.",
            "Requires rolling multi-month observation window (e.g. 13 months).", "Chessa / CBS (2016)"
        ],
        [
            "Time-Series Nowcasting", "MIDAS Regression (Mixed-Data Sampling)", "Traditional AR / ARIMA",
            "15%–35% RMSE Reduction",
            "Directly integrates high-frequency daily scraped data into monthly target forecasts without aggregation loss.",
            "Linear parameterization assumptions.", "Macias et al. (2023)"
        ],
        [
            "Time-Series Nowcasting", "Gradient Boosted Trees (GBRT / LightGBM)", "Phillips Curve / Factor Models",
            "10%–25% MSFE Reduction",
            "Captures non-linearities, threshold effects, and commodity/exchange rate shocks without overfitting.",
            "Black-box nature requires SHAP/feature importance for economic interpretability.", "Medeiros et al. (2021)"
        ]
    ]

    for row_idx, row_vals in enumerate(bench_data, 2):
        for col_idx, val in enumerate(row_vals, 1):
            c = ws3.cell(row=row_idx, column=col_idx, value=val)
            c.font = BOLD_DATA_FONT if col_idx in (1, 2, 4) else DATA_FONT
            align_h = "center" if col_idx == 1 else "left"
            c.alignment = Alignment(horizontal=align_h, vertical="top", wrap_text=True)

    col_widths3 = {1: 20, 2: 28, 3: 25, 4: 30, 5: 35, 6: 32, 7: 22}
    for col_idx, w in col_widths3.items():
        ws3.column_dimensions[get_column_letter(col_idx)].width = w

    ws3.auto_filter.ref = f"A1:G{len(bench_data)+1}"
    ws3.freeze_panes = "C2"

    # TAB 4: Cambodia CPI Official Methodology & Weights
    ws4 = wb.create_sheet(title="Cambodia CPI Methodology")
    ws4.views.sheetView[0].showGridLines = True

    headers4 = [
        "COICOP Div", "Division Name (UN Standard)", "Official Weight (%)",
        "Elementary Aggregation Method", "Division Aggregation Method",
        "Economic Rationale & Sensitivity", "Official Authority & Survey Basis"
    ]
    for col_idx, h in enumerate(headers4, 1):
        c = ws4.cell(row=1, column=col_idx, value=h)
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    khm_data = [
        ["01", "Food and Non-Alcoholic Beverages", "44.800%", "Jevons Geometric Mean", "Modified Laspeyres", "Largest expenditure share (~45%); extreme sensitivity to agricultural supply & weather.", "NIS Cambodia / CSES Household Survey"],
        ["02", "Alcoholic Beverages, Tobacco & Narcotics", "1.500%", "Jevons Geometric Mean", "Modified Laspeyres", "Excise tax driven, inelastic consumption patterns.", "NIS Cambodia / CSES Household Survey"],
        ["03", "Clothing and Footwear", "2.900%", "Jevons Geometric Mean", "Modified Laspeyres", "Subject to seasonal discounting and apparel churn.", "NIS Cambodia / CSES Household Survey"],
        ["04", "Housing, Water, Electricity, Gas & Fuels", "17.100%", "Jevons Geometric Mean", "Modified Laspeyres", "Second largest share (~17%); utility tariffs (EDC/PPWSA) & cooking gas.", "NIS Cambodia / CSES Household Survey"],
        ["05", "Furnishings & Routine Household Maintenance", "3.300%", "Jevons Geometric Mean", "Modified Laspeyres", "Durable goods, household detergents, appliances.", "NIS Cambodia / CSES Household Survey"],
        ["06", "Health", "5.600%", "Jevons Geometric Mean", "Modified Laspeyres", "Pharmaceuticals and healthcare clinic expenditures.", "NIS Cambodia / CSES Household Survey"],
        ["07", "Transport", "12.200%", "Jevons Geometric Mean", "Modified Laspeyres", "Third largest share (~12%); direct passthrough from global oil & MOC fuel prices.", "NIS Cambodia / CSES Household Survey"],
        ["08", "Communication", "3.900%", "Jevons Geometric Mean", "Modified Laspeyres", "Mobile telecom, SIM cards, ISP broadband data tariffs.", "NIS Cambodia / CSES Household Survey"],
        ["09", "Recreation and Culture", "1.900%", "Jevons Geometric Mean", "Modified Laspeyres", "Entertainment, electronics, leisure.", "NIS Cambodia / CSES Household Survey"],
        ["10", "Education", "1.500%", "Jevons Geometric Mean", "Modified Laspeyres", "Tuition fees, textbooks, stationery.", "NIS Cambodia / CSES Household Survey"],
        ["11", "Restaurants and Hotels", "3.100%", "Jevons Geometric Mean", "Modified Laspeyres", "Food away from home, street food vendors, hospitality.", "NIS Cambodia / CSES Household Survey"],
        ["12", "Miscellaneous Goods and Services", "2.200%", "Jevons Geometric Mean", "Modified Laspeyres", "Personal care, financial services, FX fees.", "NIS Cambodia / CSES Household Survey"],
        ["TOTAL", "NATIONAL HEADLINE CPI BASKET", "100.000%", "Axiomatic Jevons", "Modified Laspeyres", "Headline CPI tracks complete national cost-of-living basket.", "Royal Government of Cambodia / MoP"]
    ]

    for row_idx, row_vals in enumerate(khm_data, 2):
        for col_idx, val in enumerate(row_vals, 1):
            c = ws4.cell(row=row_idx, column=col_idx, value=val)
            is_tot = (row_vals[0] == "TOTAL")
            c.font = BOLD_DATA_FONT if (is_tot or col_idx in (1, 2, 3)) else DATA_FONT
            align_h = "center" if col_idx in (1, 3, 4, 5) else "left"
            c.alignment = Alignment(horizontal=align_h, vertical="top", wrap_text=True)

    col_widths4 = {1: 14, 2: 38, 3: 18, 4: 28, 5: 26, 6: 45, 7: 35}
    for col_idx, w in col_widths4.items():
        ws4.column_dimensions[get_column_letter(col_idx)].width = w

    ws4.auto_filter.ref = f"A1:G{len(khm_data)+1}"
    ws4.freeze_panes = "C2"

    for p in output_paths:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        wb.save(p)
        print(f"Generated clean Excel at: {p}")

if __name__ == "__main__":
    paths = [
        r"D:\CPI PIPELINE\thesis\Literature_Review_Matrix.xlsx",
        r"D:\CPI PIPELINE\Literature_Review_Matrix.xlsx"
    ]
    build_simple_excel(paths)
