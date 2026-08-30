import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def create_literature_review_excel(output_path):
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styling constants
    FONT_FAMILY = "Segoe UI"
    HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid") # Classic Navy Blue
    HEADER_FONT = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
    
    TITLE_FILL = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
    TITLE_FONT = Font(name=FONT_FAMILY, size=14, bold=True, color="FFFFFF")

    SECTION_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    ZEBRA_FILL = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
    WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    TEXT_FONT = Font(name=FONT_FAMILY, size=10, color="000000")
    TEXT_BOLD = Font(name=FONT_FAMILY, size=10, bold=True, color="000000")
    LINK_FONT = Font(name=FONT_FAMILY, size=10, color="0563C1", underline="single")
    
    THIN_BORDER = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    HEADER_BORDER = Border(
        left=Side(style='thin', color='FFFFFF'),
        right=Side(style='thin', color='FFFFFF'),
        top=Side(style='medium', color='1F4E79'),
        bottom=Side(style='medium', color='1F4E79')
    )

    # ----------------------------------------------------
    # TAB 1: Literature Review Matrix (Master Data)
    # ----------------------------------------------------
    ws_matrix = wb.create_sheet(title="Literature Review Matrix")
    ws_matrix.views.sheetView[0].showGridLines = True

    # Title Block
    ws_matrix.merge_cells("A1:K1")
    title_cell = ws_matrix["A1"]
    title_cell.value = "CAMBODIA DAILY CPI MEDALLION PIPELINE — SYSTEMATIC LITERATURE REVIEW MATRIX"
    title_cell.font = TITLE_FONT
    title_cell.fill = TITLE_FILL
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_matrix.row_dimensions[1].height = 40

    ws_matrix.merge_cells("A2:K2")
    sub_cell = ws_matrix["A2"]
    sub_cell.value = "Comprehensive Academic & Institutional Literature Synthesis (Chapter II: Literature Review)"
    sub_cell.font = Font(name=FONT_FAMILY, size=10, italic=True, color="595959")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_matrix.row_dimensions[2].height = 20

    headers = [
        "ID",
        "Pillar / Domain",
        "Study / Paper",
        "Authors",
        "Year",
        "Journal / Publisher / Outlet",
        "Key Methodology & Algorithms",
        "Dataset & Experimental Scope",
        "Reported Metrics & Empirical Results",
        "Relevance & Mapping to Cambodia CPI Pipeline",
        "DOI / Citation Link"
    ]

    ws_matrix.row_dimensions[3].height = 28
    for col_idx, header in enumerate(headers, 1):
        cell = ws_matrix.cell(row=3, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = HEADER_BORDER

    matrix_data = [
        [
            "LR-01",
            "1. High-Frequency Web Scraping",
            "The Billion Prices Project: Using Online Prices for Measurement and Research",
            "Alberto Cavallo & Roberto Rigobon",
            2016,
            "Journal of Economic Perspectives (Vol. 30, No. 2, pp. 151-178)",
            "Automated daily web scrapers, Jevons geometric mean, high-frequency online micro price tracking.",
            "Hundreds of multi-channel & pure e-commerce retailers across 22 countries; billions of individual price quotes.",
            "• Pearson correlation >0.98 with official monthly CPI in low-inflation economies (US, Germany, Japan, Brazil).\n• Detected true 20.0% inflation in Argentina (2007–2015) vs 8.0% official reported rate.\n• Detected exchange rate pass-through shocks within 3–14 days (vs 30–60 days official lag).",
            "Provides empirical foundation for daily automated crawling of Cambodian retail e-commerce platforms to eliminate publication lag and capture rapid currency/pass-through shocks.",
            "https://doi.org/10.1257/jep.30.2.151"
        ],
        [
            "LR-02",
            "1. High-Frequency Web Scraping",
            "Web scraping techniques to collect data on consumer prices and machine learning for product classification",
            "Federico Polidoro, Roberto Giannini, Rosanna Lo Conte, & Silvia Rossetti",
            2015,
            "Statistical Journal of the IAOS (Vol. 31, No. 3, pp. 447-461)",
            "Automated scraping architectures, HTML parsing pipelines, text preprocessing, Naive Bayes and Support Vector Machine (SVM) classification.",
            "Italian National Institute of Statistics (ISTAT) empirical scanner & web scraping pilot on consumer electronics and groceries.",
            "• Increased quote sample size by >100x (over two orders of magnitude).\n• Reduced field collection labor costs by >80%.\n• Classification accuracy ranged from 82% to 92.5% across product groups.",
            "Demonstrates the operational viability of substituting manual field enumerator surveys with automated web crawlers in official NSI production pipelines.",
            "https://doi.org/10.3233/SJI-150896"
        ],
        [
            "LR-03",
            "1. High-Frequency Web Scraping",
            "Practical Guide on the Use of Web Scraping for the Calculation of the Harmonised Index of Consumer Prices (HICP)",
            "Eurostat (Statistical Office of the European Communities)",
            2022,
            "Eurostat Methodological Guidelines (Luxembourg)",
            "Crawler rate-limiting, robot.txt compliance, anti-bot mitigation, missing quote handling, longitudinal product ID hashing.",
            "Standardized institutional guidelines across 27 EU National Statistical Institutes.",
            "• Standardized crawler governance, ethical scraping protocols, and data protection.\n• Codified 7-day price carry-forward and geometric imputation rules for missing scraped quotes.",
            "Directly guides the Bronze ingestion layer design, respecting robot policies, retry-backoff algorithms, and raw payload data lake storage.",
            "Eurostat Practical Guide (2022)"
        ],
        [
            "LR-04",
            "2. NLP & AI in Product Classification",
            "NLP-Enhanced Inflation Measurement Using BERT and Web Scraping",
            "Martin Berki, Vanesa Andicsova, & Milos Oravec",
            2025,
            "Frontiers in Artificial Intelligence (Vol. 8, Art. 1543026)",
            "Fine-tuned BERT transformer architecture for multi-class hierarchical text classification into 5-digit COICOP codes.",
            "Over 100,000 scraped e-commerce product titles across retail supermarkets.",
            "• Overall classification accuracy: 94.56%.\n• Weighted precision: 94.07%.\n• Outperformed rule-based regex and TF-IDF baselines on noisy, abbreviated product listings.",
            "Forms the technical foundation for the Silver classification layer, validating transformer embeddings for classifying Cambodian e-commerce items into 12 COICOP divisions.",
            "https://doi.org/10.3389/frai.2025.1543026"
        ],
        [
            "LR-05",
            "2. NLP & AI in Product Classification",
            "Project Spectrum: Using Generative AI to Enhance Inflation Nowcasting",
            "Bank for International Settlements (BIS), European Central Bank (ECB), & Deutsche Bundesbank",
            2024,
            "BIS Innovation Hub Technical Report (Basel, Switzerland)",
            "Large Language Models (LLMs), dense vector embeddings (OpenAI / Cohere), vector database caching, few-shot prompt engineering.",
            "Billions of scraped price quotes across multi-lingual European retailer catalogs.",
            "• Zero-shot & few-shot LLM reasoning achieved >95% classification precision.\n• Reduced batch processing latency from several days to <3 minutes via vector memoization and cache lookup.",
            "Validates the hybrid Silver layer architecture: using dense vector caching for instant exact match and LLM fallback for ambiguous Khmer/English product descriptions.",
            "https://www.bis.org/about/bisih/topics/ai/spectrum.htm"
        ],
        [
            "LR-06",
            "2. NLP & AI in Product Classification",
            "Using Machine Learning for Classifying Web-Scraped Data into COICOP",
            "Office for National Statistics (ONS) Data Science Campus",
            2020,
            "ONS Methodology Technical Paper (Newport, UK)",
            "FastText & TF-IDF feature extraction, XGBoost classifier, Human-in-the-Loop (HITL) operational confidence thresholding.",
            "UK web-scraped clothing and grocery price panel (millions of quotes).",
            "• Macro F1-score of 87%–91%.\n• Confidence threshold (tau = 0.80) allowed >70% of volume to be fully automated without human intervention while maintaining official statistical quality.",
            "Informs the automated Silver validation pipeline: items with classification confidence >= 0.80 pass automatically, while low-confidence items are flagged for audit.",
            "https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies"
        ],
        [
            "LR-07",
            "3. Econometric Index Number Theory",
            "Consumer Price Index Manual: Concepts and Methods",
            "IMF, ILO, OECD, Eurostat, UN, & World Bank",
            2020,
            "International Monetary Fund (Washington, D.C.)",
            "Axiomatic price index theory, elementary Jevons geometric mean, Carli/Dutot formula bias proofs, missing quote imputation, hedonic quality adjustment.",
            "Global standard methodology for national statistical offices and central banks.",
            "• Proved Jevons geometric mean satisfies time-reversal and transitivity axioms.\n• Proved Carli arithmetic mean suffers from 0.5%–1.5% upward price bounce bias.\n• Mandated Jevons formula as the global best practice for unweighted micro-level aggregation.",
            "Governs the Gold aggregation layer: proves why elementary daily micro-indices in the pipeline must use Jevons geometric averages rather than arithmetic means.",
            "ISBN: 978-1-48435-430-8"
        ],
        [
            "LR-08",
            "3. Econometric Index Number Theory",
            "Substitution Bias and Scanner Data: Measuring Price Change with Scanner Data",
            "W. Erwin Diewert & Kevin J. Fox",
            2020,
            "Journal of Econometrics (Vol. 217, No. 2, pp. 268-284)",
            "Superlative index number formulas (Fisher Ideal, Törnqvist), exact economic index theory, second-order Taylor approximations.",
            "High-frequency barcode scanner transactions across extensive supermarket chains.",
            "• Quantified that standard fixed-basket Laspeyres indices overstate inflation by 0.30%–0.85% per annum due to commodity substitution.\n• Proved superlative indices effectively eliminate substitution bias by capturing shifts toward discounted goods.",
            "Justifies the pipeline's hybrid weighting strategy, combining official CSES fixed weights with dynamic expenditure approximations.",
            "https://doi.org/10.1016/j.jeconom.2019.12.013"
        ],
        [
            "LR-09",
            "3. Econometric Index Number Theory",
            "A New Methodology for Processing Scanner Data in the Dutch CPI",
            "Antonio G. Chessa",
            2016,
            "EURONA — Eurostat Review on National Accounts (Vol. 2016, No. 1, pp. 49-69)",
            "Rolling Multilateral GEKS-Törnqvist index, Quality-Adjusted Unit Value GEKS (QU-GEKS), Movement Splice / Window Splicing (13-month rolling window).",
            "Statistics Netherlands (CBS) comprehensive supermarket scanner data panel.",
            "• Proved multilateral GEKS completely eliminates 'chain drift' (5%–10% cumulative multi-year bias caused by clearance sales and item turnover).\n• Successfully deployed into official Dutch national CPI production.",
            "Provides the theoretical framework for multilateral aggregation in the Gold layer to prevent downward chain drift caused by frequent flash sales on Cambodian e-commerce platforms.",
            "EURONA 2016(1):49-69"
        ],
        [
            "LR-10",
            "4. ML & Time-Series Nowcasting",
            "Nowcasting Food Inflation with a Massive Amount of Online Prices",
            "Pawel Macias, Damian Stelmasiak, & Karol Szafranek",
            2023,
            "International Journal of Forecasting (Vol. 39, No. 2, pp. 809-826)",
            "Mixed-Data Sampling (MIDAS), Autoregressive Distributed Lag (ARDL), daily scraped web panel aggregation for monthly macroeconomic forecasting.",
            "Over 2 million daily food quotes scraped over an 11-year longitudinal panel in Poland.",
            "• 15% to 35% reduction in Root Mean Square Error (RMSE) over standard AR/ARIMA benchmarks when predicting official monthly food CPI.\n• Superior real-time tracking during periods of high economic turbulence and supply shocks.",
            "Directly validates the Gold-to-Platinum nowcasting module: using daily scraped food & beverage sub-indices to nowcast official National Institute of Statistics (NIS) monthly inflation.",
            "https://doi.org/10.1016/j.ijforecast.2022.01.007"
        ],
        [
            "LR-11",
            "4. ML & Time-Series Nowcasting",
            "Forecasting Inflation in a Data-Rich Environment: The Benefits of Machine Learning Methods",
            "Marcelo C. Medeiros, Gabriel F. R. Vasconcelos, Alvaro Veiga, & Eduardo Zilberman",
            2021,
            "Journal of Business & Economic Statistics (Vol. 39, No. 1, pp. 98-119)",
            "Random Forests, Gradient Boosted Regression Trees (GBRT/LightGBM), LASSO, Ridge, Factor Models vs. Phillips Curve and AR benchmarks.",
            "Extensive high-dimensional US macroeconomic dataset (FRED-MD) across 1 to 12-month forecast horizons.",
            "• Tree-based ensembles (Random Forest & GBRT) significantly outperformed all linear econometric benchmarks, reducing MSFE by 10%–25%.\n• Effectively captured non-linear threshold effects and complex macro interactions between commodities, exchange rates, and prices.",
            "Informs the pipeline's multi-horizon forecasting engine, supporting gradient boosting ensembles with commodity and KHR/USD exchange rate regressors.",
            "https://doi.org/10.1080/07350015.2019.1637745"
        ]
    ]

    for row_idx, row_data in enumerate(matrix_data, 4):
        ws_matrix.row_dimensions[row_idx].height = 70
        is_zebra = (row_idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_zebra else WHITE_FILL

        for col_idx, value in enumerate(row_data, 1):
            cell = ws_matrix.cell(row=row_idx, column=col_idx, value=value)
            cell.font = TEXT_FONT
            cell.fill = row_fill
            cell.border = THIN_BORDER

            # Alignment and formatting per column
            if col_idx == 1: # ID
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = TEXT_BOLD
            elif col_idx == 2: # Pillar
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                cell.font = TEXT_BOLD
            elif col_idx in [3, 4]: # Study, Authors
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            elif col_idx == 5: # Year
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [6, 7, 8, 9, 10]: # Text details
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            elif col_idx == 11: # Link / DOI
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                if str(value).startswith("http"):
                    cell.font = LINK_FONT
                    cell.hyperlink = value

    # Set column widths for Matrix
    col_widths_matrix = {
        1: 10,  # ID
        2: 24,  # Pillar
        3: 32,  # Study
        4: 26,  # Authors
        5: 10,  # Year
        6: 28,  # Journal
        7: 35,  # Methodology
        8: 30,  # Dataset
        9: 38,  # Metrics
        10: 38, # Relevance
        11: 30  # Link
    }
    for col_idx, width in col_widths_matrix.items():
        ws_matrix.column_dimensions[get_column_letter(col_idx)].width = width

    ws_matrix.freeze_panes = "C4"
    ws_matrix.auto_filter.ref = f"A3:K{len(matrix_data)+3}"

    # ----------------------------------------------------
    # TAB 2: Thematic Pillars & Pipeline Architecture
    # ----------------------------------------------------
    ws_pillars = wb.create_sheet(title="Thematic Pillars & Pipeline")
    ws_pillars.views.sheetView[0].showGridLines = True

    # Title
    ws_pillars.merge_cells("A1:F1")
    p_title = ws_pillars["A1"]
    p_title.value = "THEMATIC RESEARCH PILLARS & MEDALLION ARCHITECTURE MAPPING"
    p_title.font = TITLE_FONT
    p_title.fill = TITLE_FILL
    p_title.alignment = Alignment(horizontal="center", vertical="center")
    ws_pillars.row_dimensions[1].height = 40

    pillar_headers = [
        "Pillar #",
        "Thematic Research Domain",
        "Core Academic & Institutional Literature",
        "Key Methodological Principles",
        "Target Medallion Layer",
        "Engineering Implementation in Cambodia Pipeline"
    ]

    ws_pillars.row_dimensions[3].height = 28
    for col_idx, header in enumerate(pillar_headers, 1):
        cell = ws_pillars.cell(row=3, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = HEADER_BORDER

    pillars_data = [
        [
            "Pillar 1",
            "High-Frequency Web Scraping & Ingestion",
            "• Cavallo & Rigobon (2016) [BPP]\n• Polidoro et al. (2015) [ISTAT]\n• Eurostat (2022) [HICP Guide]",
            "• Automated daily distributed crawlers.\n• >100x sample size expansion over manual surveys.\n• Detection of macro shocks within 3–14 days.\n• 7-day missing price carry-forward rules.",
            "Bronze Layer (Raw Ingestion)",
            "Daily Playwright/Scrapy crawlers targeting major Cambodian supermarkets (AEON, Chip Mong, Makro, Nham24) storing raw JSON/HTML payloads in PostgreSQL / Data Lake."
        ],
        [
            "Pillar 2",
            "NLP & AI in Product Classification",
            "• Berki et al. (2025) [BERT COICOP]\n• BIS / ECB / Bundesbank (2024) [Spectrum]\n• ONS Data Science Campus (2020) [XGBoost]",
            "• Dense transformer embeddings (BERT/RoBERTa).\n• Multi-class hierarchical classification into 12 COICOP divisions.\n• Few-shot LLM reasoning with vector caching.\n• Human-in-the-Loop (HITL) thresholding (tau >= 0.80).",
            "Silver Layer (Enrichment & Standardization)",
            "Hybrid text processing: vector embedding semantic search against COICOP codebook + LLM fallback for multi-lingual (Khmer/English) listings with confidence auditing."
        ],
        [
            "Pillar 3",
            "Econometric Multilateral Index Theory",
            "• IMF/ILO/UN CPI Manual (2020)\n• Diewert & Fox (2020) [Substitution Bias]\n• Chessa (2016) [GEKS / Statistics Netherlands]",
            "• Unweighted Jevons geometric mean satisfies time-reversal & transitivity.\n• Superlative Fisher/Törnqvist eliminates substitution bias (0.3%–0.85%/yr).\n• Rolling Multilateral GEKS with movement splice eliminates chain drift.",
            "Gold Layer (Aggregations & Analytics)",
            "dbt transformation models executing elementary Jevons daily indexing, aggregation into 12 COICOP groups, and multilateral GEKS adjustments for product turnover."
        ],
        [
            "Pillar 4",
            "Machine Learning & Macro Nowcasting",
            "• Macias et al. (2023) [MIDAS Nowcasting]\n• Medeiros et al. (2021) [ML Inflation]",
            "• Mixed-Data Sampling (MIDAS) bridging daily online prices to monthly official CPI.\n• 15%–35% RMSE reduction over AR/ARIMA.\n• Gradient Boosted Trees (GBRT/LightGBM) & Random Forests capturing non-linear macro interactions.",
            "Platinum Layer (Nowcasting & Dashboards)",
            "Ensemble forecasting models predicting official National Institute of Statistics (NIS) monthly CPI 20–30 days prior to official publication using daily scraped indexes + exchange rates."
        ]
    ]

    for row_idx, row_data in enumerate(pillars_data, 4):
        ws_pillars.row_dimensions[row_idx].height = 95
        is_zebra = (row_idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_zebra else WHITE_FILL

        for col_idx, value in enumerate(row_data, 1):
            cell = ws_pillars.cell(row=row_idx, column=col_idx, value=value)
            cell.font = TEXT_FONT
            cell.fill = row_fill
            cell.border = THIN_BORDER

            if col_idx == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = TEXT_BOLD
            elif col_idx == 2:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                cell.font = TEXT_BOLD
            elif col_idx == 5:
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.font = TEXT_BOLD
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    col_widths_pillars = {
        1: 12, # Pillar
        2: 26, # Domain
        3: 32, # Literature
        4: 38, # Principles
        5: 22, # Layer
        6: 45  # Implementation
    }
    for col_idx, width in col_widths_pillars.items():
        ws_pillars.column_dimensions[get_column_letter(col_idx)].width = width

    ws_pillars.freeze_panes = "C4"

    # ----------------------------------------------------
    # TAB 3: Models & Metrics Benchmark
    # ----------------------------------------------------
    ws_bench = wb.create_sheet(title="Methodology & Metrics Benchmark")
    ws_bench.views.sheetView[0].showGridLines = True

    # Title
    ws_bench.merge_cells("A1:G1")
    b_title = ws_bench["A1"]
    b_title.value = "METHODOLOGICAL BENCHMARK & METRIC TAXONOMY"
    b_title.font = TITLE_FONT
    b_title.fill = TITLE_FILL
    b_title.alignment = Alignment(horizontal="center", vertical="center")
    ws_bench.row_dimensions[1].height = 40

    bench_headers = [
        "Category",
        "Algorithm / Formula",
        "Benchmark / Baseline",
        "Key Metric / Reported Performance",
        "Advantages",
        "Limitations / Tradeoffs",
        "Reference Paper"
    ]

    ws_bench.row_dimensions[3].height = 28
    for col_idx, header in enumerate(bench_headers, 1):
        cell = ws_bench.cell(row=3, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = HEADER_BORDER

    bench_data = [
        [
            "NLP Classification",
            "BERT Transformer (Fine-Tuned)",
            "TF-IDF + Naive Bayes / SVM",
            "94.56% Accuracy, 94.07% Precision",
            "Deep contextual semantic understanding; handles abbreviations, brands, packaging nuances.",
            "Higher computational footprint; requires GPU or inference optimization.",
            "Berki et al. (2025)"
        ],
        [
            "NLP Classification",
            "LLM + Vector Cache (Project Spectrum)",
            "Handcrafted Regex Rules",
            ">95% Precision, Latency <3 min",
            "Zero-shot/few-shot multi-lingual adaptation (Khmer/English); fast retrieval via caching.",
            "API token costs; potential non-deterministic hallucinations if unconstrained.",
            "BIS / ECB / Bundesbank (2024)"
        ],
        [
            "NLP Classification",
            "FastText + XGBoost with HITL (tau=0.80)",
            "Manual Field Survey Categorization",
            "87%–91% Macro F1, >70% Automated",
            "Lightweight, deterministic confidence scores; high throughput for automated pipelines.",
            "Slightly lower accuracy on rare out-of-vocabulary product items.",
            "ONS Data Science Campus (2020)"
        ],
        [
            "Index Calculation",
            "Jevons Geometric Mean",
            "Carli Arithmetic Mean / Dutot Ratio",
            "Eliminates 0.5%–1.5% Upward Bias",
            "Axiomatically sound (satisfies time-reversal & transitivity); standard for unweighted micro prices.",
            "Cannot handle zero prices without imputation or shift constants.",
            "IMF CPI Manual (2020)"
        ],
        [
            "Index Calculation",
            "Superlative Indices (Fisher / Törnqvist)",
            "Fixed-base Laspeyres Index",
            "Removes 0.3%–0.85%/yr Substitution Bias",
            "Exact second-order approximation to true cost of living; accommodates consumer substitution.",
            "Requires simultaneous real-time quantity/expenditure weights.",
            "Diewert & Fox (2020)"
        ],
        [
            "Index Calculation",
            "Rolling Multilateral GEKS (Movement Splice)",
            "Direct Bilateral Chained Indices",
            "Eliminates 5%–10% Cumulative Chain Drift",
            "Prevents multi-year downward/upward drift caused by clearance sales and item turnover.",
            "Requires rolling multi-month observation window (e.g. 13 months).",
            "Chessa / CBS (2016)"
        ],
        [
            "Time-Series Nowcasting",
            "MIDAS Regression (Mixed-Data Sampling)",
            "Traditional AR / ARIMA",
            "15%–35% RMSE Reduction",
            "Directly integrates high-frequency daily scraped data into monthly target forecasts without aggregation loss.",
            "Linear parameterization assumptions.",
            "Macias et al. (2023)"
        ],
        [
            "Time-Series Nowcasting",
            "Gradient Boosted Trees (GBRT / LightGBM)",
            "Phillips Curve / Factor Models",
            "10%–25% MSFE Reduction",
            "Captures non-linearities, threshold effects, and commodity/exchange rate shocks without overfitting.",
            "Black-box nature requires SHAP/feature importance for economic interpretability.",
            "Medeiros et al. (2021)"
        ]
    ]

    for row_idx, row_data in enumerate(bench_data, 4):
        ws_bench.row_dimensions[row_idx].height = 65
        is_zebra = (row_idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_zebra else WHITE_FILL

        for col_idx, value in enumerate(row_data, 1):
            cell = ws_bench.cell(row=row_idx, column=col_idx, value=value)
            cell.font = TEXT_FONT
            cell.fill = row_fill
            cell.border = THIN_BORDER

            if col_idx == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = TEXT_BOLD
            elif col_idx == 2:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                cell.font = TEXT_BOLD
            elif col_idx == 4:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                cell.font = TEXT_BOLD
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    col_widths_bench = {
        1: 20, # Category
        2: 28, # Algorithm
        3: 25, # Benchmark
        4: 30, # Metric
        5: 35, # Advantages
        6: 32, # Limitations
        7: 22  # Reference
    }
    for col_idx, width in col_widths_bench.items():
        ws_bench.column_dimensions[get_column_letter(col_idx)].width = width

    ws_bench.freeze_panes = "C4"

    # ----------------------------------------------------
    # TAB 4: Cambodia CPI Official Methodology & Weights
    # ----------------------------------------------------
    ws_khm = wb.create_sheet(title="Cambodia CPI Methodology")
    ws_khm.views.sheetView[0].showGridLines = True

    # Title
    ws_khm.merge_cells("A1:G1")
    k_title = ws_khm["A1"]
    k_title.value = "OFFICIAL CAMBODIA CPI METHODOLOGY & EXPENDITURE BASKET (NIS / IMF)"
    k_title.font = TITLE_FONT
    k_title.fill = TITLE_FILL
    k_title.alignment = Alignment(horizontal="center", vertical="center")
    ws_khm.row_dimensions[1].height = 40

    ws_khm.merge_cells("A2:G2")
    k_sub = ws_khm["A2"]
    k_sub.value = "Two-Stage Aggregation: Jevons Geometric Mean (Elementary Items) + Modified Laspeyres (12 COICOP Divisions)"
    k_sub.font = Font(name=FONT_FAMILY, size=10, italic=True, color="595959")
    k_sub.alignment = Alignment(horizontal="center", vertical="center")
    ws_khm.row_dimensions[2].height = 20

    khm_headers = [
        "COICOP Div",
        "Division Name (UN Standard)",
        "Official Weight (%)",
        "Elementary Aggregation Method",
        "Division Aggregation Method",
        "Economic Rationale & Sensitivity",
        "Official Authority & Survey Basis"
    ]

    ws_khm.row_dimensions[3].height = 28
    for col_idx, header in enumerate(khm_headers, 1):
        cell = ws_khm.cell(row=3, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = HEADER_BORDER

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

    for row_idx, row_data in enumerate(khm_data, 4):
        ws_khm.row_dimensions[row_idx].height = 40
        is_total = (row_data[0] == "TOTAL")
        is_zebra = (row_idx % 2 == 0) and not is_total
        
        row_fill = SECTION_FILL if is_total else (ZEBRA_FILL if is_zebra else WHITE_FILL)
        row_font = Font(name=FONT_FAMILY, size=10, bold=is_total, color="1F4E79" if is_total else "000000")

        for col_idx, value in enumerate(row_data, 1):
            cell = ws_khm.cell(row=row_idx, column=col_idx, value=value)
            cell.font = row_font
            cell.fill = row_fill
            cell.border = THIN_BORDER

            if col_idx in [1, 3, 4, 5]:
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    col_widths_khm = {
        1: 14, # Code
        2: 38, # Name
        3: 18, # Weight
        4: 28, # Elementary
        5: 26, # Higher
        6: 45, # Rationale
        7: 35  # Source
    }
    for col_idx, width in col_widths_khm.items():
        ws_khm.column_dimensions[get_column_letter(col_idx)].width = width

    ws_khm.freeze_panes = "C4"

    # Save workbook
    wb.save(output_path)
    print(f"Workbook successfully saved to: {output_path}")

if __name__ == "__main__":
    create_literature_review_excel(r"D:\CPI PIPELINE\thesis\Literature_Review_Matrix.xlsx")
    create_literature_review_excel(r"D:\CPI PIPELINE\Literature_Review_Matrix.xlsx")
