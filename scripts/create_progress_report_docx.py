import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex)
    tcPr.append(shd)

def set_cell_margins(cell, top=60, bottom=60, left=100, right=100):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_table_borders(table, color="D0D5DD", sz="4", val="single"):
    tblPr = table._tbl.tblPr
    tblBorders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), val)
        border.set(qn('w:sz'), sz)
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), color)
        tblBorders.append(border)
    border = OxmlElement('w:insideV')
    border.set(qn('w:val'), 'none')
    tblBorders.append(border)
    tblPr.append(tblBorders)

def build_docx(filename="Cambodia_CPI_Project_Progress_Report.docx"):
    doc = Document()
    
    # ── Page Margins (0.65 in) ────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin = Inches(0.60)
        section.bottom_margin = Inches(0.60)
        section.left_margin = Inches(0.65)
        section.right_margin = Inches(0.65)
        
        # Header
        hp = section.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run("Project Progress · Nowcasting Inflation via Daily Web Scraping Price")
        hrun.font.name = "Calibri"
        hrun.font.size = Pt(8.5)
        hrun.font.color.rgb = RGBColor(120, 120, 120)
        
        # Footer
        fp = section.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        frun = fp.add_run("Author: TAING Korngmeng | GDDE / MEF & ITC")
        frun.font.name = "Calibri"
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = RGBColor(120, 120, 120)

    # ── Colors ────────────────────────────────────────────────────────────────
    NAVY = RGBColor(12, 44, 98)      # #0C2C62
    TEAL = RGBColor(20, 110, 120)    # #146E78
    DARK = RGBColor(33, 37, 41)

    # ── Title & Subtitle ──────────────────────────────────────────────────────
    p_prog = doc.add_paragraph()
    p_prog.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_prog.paragraph_format.space_before = Pt(0)
    p_prog.paragraph_format.space_after = Pt(2)
    r_prog = p_prog.add_run("Project Progress")
    r_prog.font.name = "Calibri"
    r_prog.font.size = Pt(13)
    r_prog.font.bold = True
    r_prog.font.color.rgb = TEAL

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(12)
    r_title = p_title.add_run("Nowcasting Inflation via Daily Web Scraping Price")
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(20)
    r_title.font.bold = True
    r_title.font.color.rgb = NAVY

    # ── 1. OBJECTIVE ──────────────────────────────────────────────────────────
    h1 = doc.add_heading("1. Objective", level=1)
    h1.paragraph_format.space_before = Pt(6)
    h1.paragraph_format.space_after = Pt(4)

    objectives = [
        ("Build an Automated Data Infrastructure and Monitoring System: ", 
         "Set up an automated data pipeline and database to collect, store, and continuously monitor price."),
        ("Calculate CPI for inflation nowcasting using machine learning model: ", 
         "Apply an economic formula to compute daily price relatives, and use regularized Ridge regression modeling to nowcast inflation ahead of the official monthly release."),
        ("Build a decision-support dashboard: ", 
         "Develop an interactive dashboard that presents daily CPI results and inflation for easy monitoring.")
    ]

    for title, text in objectives:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(title)
        r.font.bold = True
        r.font.color.rgb = NAVY
        p.add_run(text)

    # ── 2. ARCHITECTURE ───────────────────────────────────────────────────────
    h2 = doc.add_heading("2. Architecture", level=1)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)

    # Insert Architecture Diagram if available
    img_path = r"D:\CPI PIPELINE\thesis\images\cpi_architecture_clean.png"
    if os.path.exists(img_path):
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(4)
        p_img.paragraph_format.space_after = Pt(2)
        doc.add_picture(img_path, width=Inches(5.0))
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_after = Pt(6)
        r_c = p_cap.add_run("Figure 1: End-to-End System Architecture: Web Scraping, Medallion Pipeline & Dashboard.")
        r_c.font.size = Pt(8.5)
        r_c.font.italic = True
        r_c.font.color.rgb = RGBColor(100, 100, 100)

    h2_tech = doc.add_heading("Technology Stack", level=2)
    h2_tech.paragraph_format.space_before = Pt(4)
    h2_tech.paragraph_format.space_after = Pt(4)

    tech_stack = [
        ("Data Ingestion & Scraping", "Python"),
        ("Database and Storage", "Postgres 16"),
        ("Orchestration", "Apache Airflow"),
        ("Data Transformation", "dbt Core"),
        ("AI Product Classifications", "Gemini AI"),
        ("Dashboard and Monitoring", "Metabase"),
        ("System Container", "Docker")
    ]

    tbl_tech = doc.add_table(rows=len(tech_stack) + 1, cols=2)
    tbl_tech.alignment = WD_TABLE_ALIGNMENT.CENTER
    t_widths = [Inches(3.5), Inches(3.5)]

    # Header Row
    for idx, htext in enumerate(["Component / Layer", "Technology Stack"]):
        cell = tbl_tech.cell(0, idx)
        cell.width = t_widths[idx]
        set_cell_background(cell, "0C2C62")
        set_cell_margins(cell, top=40, bottom=40, left=80, right=80)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(htext)
        run.font.name = "Calibri"
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, (layer, tech) in enumerate(tech_stack):
        bg = "F8F9FA" if row_idx % 2 == 1 else "FFFFFF"
        cell_l = tbl_tech.cell(row_idx + 1, 0)
        cell_r = tbl_tech.cell(row_idx + 1, 1)
        cell_l.width = t_widths[0]
        cell_r.width = t_widths[1]
        set_cell_background(cell_l, bg)
        set_cell_background(cell_r, bg)
        set_cell_margins(cell_l, top=35, bottom=35, left=80, right=80)
        set_cell_margins(cell_r, top=35, bottom=35, left=80, right=80)

        p1 = cell_l.paragraphs[0]
        p1.paragraph_format.space_after = Pt(0)
        r1 = p1.add_run(layer)
        r1.font.name = "Calibri"
        r1.font.size = Pt(8.5)
        r1.font.bold = True

        p2 = cell_r.paragraphs[0]
        p2.paragraph_format.space_after = Pt(0)
        r2 = p2.add_run(tech)
        r2.font.name = "Calibri"
        r2.font.size = Pt(8.5)

    set_table_borders(tbl_tech, color="D0D5DD")

    doc.add_page_break()

    # ── 3. DATA COLLECTION ────────────────────────────────────────────────────
    h3 = doc.add_heading("3. Data Collection", level=1)
    h3.paragraph_format.space_before = Pt(0)
    h3.paragraph_format.space_after = Pt(4)

    sources_data = [
        ("AEON Online Cambodia", "Supermarket"),
        ("DeliShop Asia Phnom Penh", "Supermarket"),
        ("GrabMart (Lucky Supermarket, Chip Mong)", "Supermarket"),
        ("L192 Online Marketplace", "Footwear & Homeware"),
        ("Community Pharmacy & Ucare Pharmacy", "Healthcare & Pharmaceutical Goods"),
        ("Khmer24 & Realestate.com.kh", "Urban Residential Apartment, House Rentals"),
        ("redBus & BookMeBus Transit", "Bus & Travel Transport"),
        ("Cellcard, Smart Axiata, Metfone", "Mobile plan and Wi-Fi"),
        ("Tela Khmer", "Gasoline"),
        ("dataEF API", "Exchange rate"),
        ("Sokha, Hyatt, Bayon BKK", "Restaurant and hotel")
    ]

    tbl_src = doc.add_table(rows=len(sources_data) + 1, cols=2)
    tbl_src.alignment = WD_TABLE_ALIGNMENT.CENTER
    s_widths = [Inches(3.5), Inches(3.5)]

    for idx, htext in enumerate(["Data Source", "Description"]):
        cell = tbl_src.cell(0, idx)
        cell.width = s_widths[idx]
        set_cell_background(cell, "0C2C62")
        set_cell_margins(cell, top=40, bottom=40, left=80, right=80)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(htext)
        run.font.name = "Calibri"
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, (src, desc) in enumerate(sources_data):
        bg = "F8F9FA" if row_idx % 2 == 1 else "FFFFFF"
        cell_l = tbl_src.cell(row_idx + 1, 0)
        cell_r = tbl_src.cell(row_idx + 1, 1)
        cell_l.width = s_widths[0]
        cell_r.width = s_widths[1]
        set_cell_background(cell_l, bg)
        set_cell_background(cell_r, bg)
        set_cell_margins(cell_l, top=35, bottom=35, left=80, right=80)
        set_cell_margins(cell_r, top=35, bottom=35, left=80, right=80)

        p1 = cell_l.paragraphs[0]
        p1.paragraph_format.space_after = Pt(0)
        r1 = p1.add_run(src)
        r1.font.name = "Calibri"
        r1.font.size = Pt(8.5)
        r1.font.bold = True

        p2 = cell_r.paragraphs[0]
        p2.paragraph_format.space_after = Pt(0)
        r2 = p2.add_run(desc)
        r2.font.name = "Calibri"
        r2.font.size = Pt(8.5)

    set_table_borders(tbl_src, color="D0D5DD")

    p_sp2 = doc.add_paragraph()
    p_sp2.paragraph_format.space_before = Pt(4)
    p_sp2.paragraph_format.space_after = Pt(4)

    # ── 4. METHODOLOGY ────────────────────────────────────────────────────────
    h4 = doc.add_heading("4. Methodology", level=1)
    h4.paragraph_format.space_before = Pt(6)
    h4.paragraph_format.space_after = Pt(4)

    # Stage 1
    doc.add_heading("Stage 1: Web Scraping Layer", level=2)
    p_sc = doc.add_paragraph()
    p_sc.paragraph_format.space_after = Pt(2)
    p_sc.add_run("Automated Daily Collection: ").font.bold = True
    p_sc.add_run("Every morning at 08:00 AM, the system automatically collects prices across 11 key stores and services in Cambodia.")

    p_pm = doc.add_paragraph()
    p_pm.paragraph_format.space_before = Pt(3)
    p_pm.paragraph_format.space_after = Pt(2)
    p_pm.add_run("How We Collect Prices:").font.bold = True

    scrape_methods = [
        ("Direct Store APIs: ", "Connects directly to the backend of online supermarkets (AEON, DeliShop) and apps (L192, BookMeBus) to download product lists and prices quickly without loading heavy web pages."),
        ("Browser Disguise (curl_cffi): ", "Sends fast automated requests that look like a real Google Chrome browser so store security systems (like Cloudflare) do not block our computer."),
        ("Invisible Browser (Playwright): ", "If a website blocks direct requests with security checks (like 403 Forbidden), the system automatically opens an invisible browser to load the page and read the prices like a real user."),
        ("Public Pages & Feeds: ", "Reads apartment rental listings from Khmer24, fuel prices from the Tela Khmer public channel (translating Khmer numbers 0-9), and official daily exchange rates from the Ministry of Economy and Finance (MEF)."),
        ("Safety & Backup Rules: ", "Pauses 1 second between requests so we do not slow down store websites, and sends an alert if 0 products are found so bad data is never saved.")
    ]
    for sm_t, sm_d in scrape_methods:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(sm_t).font.bold = True
        p.add_run(sm_d)

    # Stage 2
    doc.add_heading("Stage 2: Bronze Layer (Raw Lake Ingestion)", level=2)
    p_b_table = doc.add_paragraph()
    p_b_table.paragraph_format.space_after = Pt(2)
    p_b_table.add_run("Database Table: ").font.bold = True
    p_b_table.add_run("bronze.raw_prices")

    bronze_points = [
        ("What it does: ", "Acts as an immutable, append-only raw data repository preserving the exact raw data as fetched from the web."),
        ("Stored Fields: ", "store_id, source_name, item_description_raw, price, currency, source_url, scraped_at, batch_id.")
    ]
    for b_t, b_d in bronze_points:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(b_t).font.bold = True
        p.add_run(b_d)

    doc.add_page_break()

    # ── Stage 3: Silver Layer ─────────────────────────────────────────────────
    doc.add_heading("Stage 3: Silver Layer (Data Preprocessing, Matching & AI Classification)", level=2)
    p_s_table = doc.add_paragraph()
    p_s_table.paragraph_format.space_after = Pt(2)
    p_s_table.add_run("Database Table: ").font.bold = True
    p_s_table.add_run("silver.standardized_prices\n")
    p_s_table.add_run("The Silver Layer has 3 main jobs:\n")
    r_flow = p_s_table.add_run("[Raw Scrape] ──► 1. Clean Data ──► 2. Match Product ──► 3. Classify Basket ──► [Clean Silver Item]")
    r_flow.font.bold = True
    r_flow.font.color.rgb = NAVY

    # 4.3.1 Data Cleaning & Standardization
    doc.add_heading("4.3.1 Data Cleaning & Standardization", level=3)
    clean_points = [
        ("Clean product names and text: ", "Remove HTML, special characters, promotional words (SALE, HOT DEAL, 50% OFF), unnecessary text, and convert text to lowercase."),
        ("Convert Khmer numerals → Arabic numerals: ", "Convert Khmer digits (e.g., ៥០០ → 500) for consistent processing."),
        ("Convert USD → KHR: ", "Convert dual currencies using the official MEF daily exchange rate."),
        ("Standardize weight, volume, and package units: ", "Convert package sizes into standard metric units (e.g., 500g to 0.5kg, 1500ml to 1.5L)."),
        ("Calculate unit prices (KHR/kg, KHR/L, etc.): ", "Compute unit price (P_unit = Price in KHR / Normalized Metric) to fairly compare different product sizes.")
    ]
    for ct, cd in clean_points:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(ct).font.bold = True
        p.add_run(cd)

    # 4.3.2 Product Matching
    doc.add_heading("4.3.2 Product Matching (4-Level Waterfall)", level=3)
    doc.add_paragraph("Connects identical products across different stores and tracks them day-after-day:")

    # Level 1
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    p.add_run("Level 1 — Barcode (GTIN / EAN): ").font.bold = True
    p.add_run("Matches the exact same item across different stores (e.g., AEON ↔ DeliShop) using global standard barcodes.")

    # Level 2
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    p.add_run("Level 2 — Store ID + SKU (Composite Key): ").font.bold = True
    p.add_run("Remembers the item day-after-day within the same store (AEON yesterday ↔ AEON today).")

    sku_points = [
        ("What is SKU? ", "A unique Stock Keeping Unit code assigned by a store, extracted directly from product URLs or store APIs."),
        ("The Problem: ", "Different stores reuse the same SKU number (e.g., SKU 100 at AEON is Beef Curry, but at DeliShop is Fruit Syrup)."),
        ("The Solution (Composite Key): ", "Combines (store_id, sku) so each store catalog remains strictly isolated."),
        ("Learn Once, Cache Forever: ", "The first time an item is scraped, it is saved into canonical tables. On daily scrapes, the system instantly recognizes it without re-matching.")
    ]
    for st, sd in sku_points:
        sp = doc.add_paragraph(style='List Bullet')
        sp.paragraph_format.space_before = Pt(1)
        sp.paragraph_format.space_after = Pt(1)
        sp.add_run(st).font.bold = True
        sp.add_run(sd)

    # Level 3
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    p.add_run("Level 3 — Exact Text Matching: ").font.bold = True
    p.add_run("Links different stores selling the exact same product when no barcode is available.")

    text_points = [
        ("When Triggered? ", "When no universal barcode is provided and the store SKU is unseen."),
        ("Why Needed? ", "Different stores assign different SKUs to the exact same item (e.g., AEON SKU 123 vs. AryStore SKU 999 for 'Samsung Galaxy A27 128GB' at $250 vs $240). Without text matching, the system would mistakenly treat them as two different items."),
        ("How We Connect Them: ", "Ignores store SKUs and matches on the cleaned product title and package size to link both stores to the exact same item.")
    ]
    for tt, td in text_points:
        tp = doc.add_paragraph(style='List Bullet')
        tp.paragraph_format.space_before = Pt(1)
        tp.paragraph_format.space_after = Pt(1)
        tp.add_run(tt).font.bold = True
        tp.add_run(td)

    # Level 4
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    p.add_run("Level 4 — Vector Embedding + Deterministic Spec Guard: ").font.bold = True
    p.add_run("Matches English and Khmer equivalents and catches minor product title variations using machine learning.")

    vec_points = [
        ("What is Vector Embedding? ", "A technique that converts words and sentences into a 768-dimensional sequence of numbers (vector) in high-dimensional semantic space."),
        ("Stage 1 (Fast Vector Search): ", "Converts cleaned title into a 768-dim embedding (gemini-embedding-2) and searches silver.canonical_items using PostgreSQL pgvector HNSW Cosine Index to return the Top 30 candidate matches."),
        ("Stage 2 (Deterministic Spec Guard): ", "Inspects physical specs of Top 30 candidates to automatically REJECT false merges:"),
        ("  • Pack Count Rejection: ", "'1 can' != '24-pack carton' ──► REJECTED"),
        ("  • Storage Rejection: ", "'128GB' != '256GB' ──► REJECTED"),
        ("Decision Rule: ", "Match approved if Cosine Similarity ≥ 0.80 and passes Spec Guard ──► Merged into True Canonical Item. Otherwise, split as a new item.")
    ]
    for vt, vd in vec_points:
        vp = doc.add_paragraph(style='List Bullet')
        vp.paragraph_format.space_before = Pt(1)
        vp.paragraph_format.space_after = Pt(1)
        vp.add_run(vt).font.bold = True
        vp.add_run(vd)

    # 4.3.3 AI Classification
    doc.add_heading("4.3.3 AI Classification into Official COICOP Baskets", level=3)
    p_coicop_def = doc.add_paragraph()
    p_coicop_def.paragraph_format.space_before = Pt(1)
    p_coicop_def.paragraph_format.space_after = Pt(2)
    p_coicop_def.add_run("What is COICOP? ").font.bold = True
    p_coicop_def.add_run("Classification of Individual Consumption According to Purpose. It is the official standard used by the United Nations and Cambodia's National Institute of Statistics (NIS) to group products to calculate CPI.")

    doc.add_paragraph("Two-Tier Classification Process:").runs[0].font.bold = True
    coicop_tiers = [
        ("Tier 1 — Store-Specific Matching: ", "For single-category stores, the database automatically assigns both the 2-digit division and exact 5-digit subclass without calling AI. Examples: Telecom (Smart, Cellcard) ──► 08 | 08.3.0 (Telephone & Internet Services); Transport (BookMeBus) ──► 07 | 07.3.2 (Passenger Road Transport)."),
        ("Tier 2 — Gemini AI (Supermarkets & Multi-Category): ", "For broad stores (AEON, DeliShop, Lucky), products are sent in batches of 40 to Gemini AI to assign the official NIS 5-digit code. Rotates across 4 API keys with 30s cooldown, returning structured JSON directly into PostgreSQL."),
        ("The 'Learn Once, Cache Forever' Strategy: ", "Products are classified on their first scrape and stored permanently in the database. Daily runs match existing items and skip AI classification entirely, only sending truly new products.")
    ]
    for ct, cd in coicop_tiers:
        cp = doc.add_paragraph(style='List Bullet')
        cp.paragraph_format.space_before = Pt(1)
        cp.paragraph_format.space_after = Pt(1)
        cp.add_run(ct).font.bold = True
        cp.add_run(cd)

    p_gr = doc.add_paragraph()
    p_gr.paragraph_format.space_before = Pt(2)
    p_gr.paragraph_format.space_after = Pt(2)
    p_gr.add_run("Strict Guardrails prevent AI mistakes:").font.bold = True
    guardrails = [
        ("Pet Food: ", "Goes to Pets (09.3.1), never human food."),
        ("Shampoo / Soap: ", "Goes to Personal Care (12.1.3), never food."),
        ("Beer / Wine: ", "Goes to Alcohol (02.1), isolated from soft drinks.")
    ]
    for gt, gd in guardrails:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        p.add_run(gt).font.bold = True
        p.add_run(gd)

    doc.add_page_break()

    # ── Stage 4.4: CPI Calculation ───────────────────────────────────────────
    doc.add_heading("4.4 CPI Calculation (From Thousands of Scraped Prices to One CPI Number)", level=2)

    p_cpi_flow = doc.add_paragraph()
    p_cpi_flow.paragraph_format.space_after = Pt(3)
    p_cpi_flow.add_run("Calculation Aggregation Pipeline:\n").font.bold = True
    r_pipe = p_cpi_flow.add_run("Product Quote ──► Relative Price ──► Store-Level Jevons ──► Elementary Aggregation ──► Class Weight ──► Group Weight ──► Division Weight ──► National CPI")
    r_pipe.font.bold = True
    r_pipe.font.color.rgb = NAVY

    # 4.4.1 Relative Price
    doc.add_heading("4.4.1 Relative Price", level=3)
    doc.add_paragraph("How do we track a product's price change relative to the baseline?")
    p_rel = doc.add_paragraph()
    p_rel.paragraph_format.space_before = Pt(1)
    p_rel.paragraph_format.space_after = Pt(2)
    r_rform = p_rel.add_run("r_{i, s, t} = P_{i, s, t} / P_{i, s, 0}\n")
    r_rform.font.bold = True
    r_rform.font.color.rgb = TEAL
    p_rel.add_run("Where:\n• i: specific item | s: specific store | t: current date | e: elementary aggregate (subclass/class)\n• P_{i, s, t}: price of item i at store s on day t\n• P_{i, s, 0}: reference base price of item i at store s\n• r > 1: price increase | r < 1: price decrease")

    # 4.4.2 Store-Level Jevons & Elementary Aggregation
    doc.add_heading("4.4.2 Store-Level Jevons & Elementary Aggregation", level=3)
    doc.add_paragraph("Within each store and product category, the pipeline calculates the unweighted geometric mean (Jevons formula) using numerical log-prices to prevent arithmetic distortion and floating-point errors:")
    p_jev_eq = doc.add_paragraph()
    p_jev_eq.paragraph_format.space_before = Pt(1)
    p_jev_eq.paragraph_format.space_after = Pt(2)
    r_jeveq = p_jev_eq.add_run("ln I_{s, t}^{Jevons} = (1 / n) ∑ (ln P_{i, s, t} - ln P_{i, s, 0})\n")
    r_jeveq.font.bold = True
    r_jeveq.font.color.rgb = TEAL
    p_jev_eq.add_run("Store-level indices are then aggregated across all eligible stores to compute the Elementary Aggregate index for category e at day t.")

    # 4.4.4 Higher-Level Aggregation
    doc.add_heading("4.4.4 Higher-Level Aggregation (Laspeyres CSES 2020 Weights)", level=3)
    doc.add_paragraph("To reflect Cambodian household spending, the 12 COICOP divisions are synthesized using official CSES 2020 survey weights:")
    p_lasp = doc.add_paragraph()
    p_lasp.paragraph_format.space_before = Pt(1)
    p_lasp.paragraph_format.space_after = Pt(2)
    r_eq2 = p_lasp.add_run("Headline CPI = ∑ ( Weight_j × Division_Index_j )")
    r_eq2.font.bold = True
    r_eq2.font.color.rgb = TEAL

    lasp_weights = [
        ("Food & Drinks (01): ", "44.775% (Highest weight in Cambodia)"),
        ("Housing & Electricity (04): ", "17.062%"),
        ("Transport & Fuel (07): ", "12.203%"),
        ("All other 9 Divisions: ", "Remaining 25.960% (Clothing, Health, Telecom, etc.)"),
        ("Refined Core CPI: ", "Excludes volatile Food (01) and Energy (04) to measure underlying long-term price stability.")
    ]
    for lt, ld in lasp_weights:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        p.add_run(lt).font.bold = True
        p.add_run(ld)

    # 4.4.5 Chain-Linking
    doc.add_heading("4.4.5 Chain-Linking (Connecting to Official NIS & Rolling into Next Year)", level=3)
    p_cl1 = doc.add_paragraph()
    p_cl1.paragraph_format.space_after = Pt(2)
    p_cl1.add_run("1. Connecting to Official NIS Benchmark (Base Converter):\n").font.bold = True
    p_cl1.add_run("• What is the problem? NIS started measuring in 2006 at 100. Over 20 years, prices doubled and their August CPI reached 219.007. Our web scraper started August 18, 2026 at 100. How can we compare NIS 219 vs. Our 99.76%?\n")
    p_cl1.add_run("• The Solution (Converter / Splicing): We multiply our monthly index by the official base factor (219.007 / 100 = 2.19007). If our calculated August index is 99.76%, then: 99.76 × 2.19007 = 218.47. Now our daily results are directly comparable to official NIS releases.")

    p_cl2 = doc.add_paragraph()
    p_cl2.paragraph_format.space_before = Pt(3)
    p_cl2.paragraph_format.space_after = Pt(2)
    p_cl2.add_run("2. Annual Chain-Linking (December Overlap — Rolling into Next Year):\n").font.bold = True
    p_cl2.add_run("• The Problem: What happens when December ends and the basket resets? If January resets back to 100.0, the graph shows a fake collapse.\n")
    p_cl2.add_run("• The Solution: We calculate the December monthly average (e.g., 105.0). The new series starts fresh at 100.0, but is multiplied by 1.05.\n")
    p_cl2.add_run("• Result: Discontinued items cleanly exit; new products become official base; and the multi-year index climbs continuously with zero New Year cliffs.")

    # 4.4.7 Missing Price & Out of Stock
    doc.add_heading("4.4.7 Missing Price & Out-of-Stock Handling", level=3)
    doc.add_paragraph("When an item is missing from today's scrape, how do we handle it?")
    miss_rules = [
        ("Why we cannot drop it immediately: ", "The basket would change size every day, creating fake jumps when the item returns in stock."),
        ("Why we cannot set price to $0: ", "The entire category index would collapse to 0."),
        ("Why we cannot freeze last price indefinitely: ", "If prices are rising across the market, freezing the price pretends inflation is lower than it really is."),
        ("Our Solution (ILO Class-Mean Imputation): ", "When an item is temporarily out-of-stock, its price is estimated using the average price change of similar products in the same category. If missing for more than a week (7 days), the item is recognized as discontinued and cleanly dropped from active calculation.")
    ]
    for mrt, mrd in miss_rules:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(mrt).font.bold = True
        p.add_run(mrd)

    # Stage 4: Nowcasting
    doc.add_heading("Stage 4: Nowcasting", level=2)
    p_now_m = doc.add_paragraph()
    p_now_m.paragraph_format.space_after = Pt(2)
    p_now_m.add_run("Methodology (Two-Tier Hybrid Approach): ").font.bold = True
    p_now_m.add_run("Rather than using a black-box AI model, we use a hybrid economic approach:")

    now_tiers = [
        ("Tier 1 (Official Aggregation): ", "We use fixed CSES expenditure weights across all 12 COICOP divisions following official NIS/ILO Laspeyres standards. We calculate both Headline CPI and Core CPI (excluding volatile food and energy)."),
        ("Tier 2 (Forward Econometric Projection): ", "For past observed days, we compute the realized daily average from scraped prices. For the unobserved remaining days of the month, we nowcast daily drift rates using regularized Ridge Regression (RidgeCV) with Bayesian prior shrinkage."),
        ("Blending: ", "We combine realized days and projected days using a time-weighted formula that smoothly converges onto actual data as the month ends.")
    ]
    for tt, td in now_tiers:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(tt).font.bold = True
        p.add_run(td)

    # Nowcasting Flowchart Image
    flowchart_path = os.path.join(os.path.dirname(__file__), "..", "thesis", "images", "nowcasting_flowchart.png")
    if os.path.exists(flowchart_path):
        p_fc = doc.add_paragraph()
        p_fc.paragraph_format.space_before = Pt(6)
        p_fc.paragraph_format.space_after = Pt(2)
        p_fc.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_fc.add_run().add_picture(flowchart_path, width=Inches(5.8))
        
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_before = Pt(1)
        p_cap.paragraph_format.space_after = Pt(6)
        r_cap = p_cap.add_run("Figure 2: Architecture Flowchart of the Two-Tier Inflation Nowcasting Engine")
        r_cap.font.name = "Calibri"
        r_cap.font.size = Pt(8.5)
        r_cap.font.italic = True
        r_cap.font.color.rgb = RGBColor(100, 100, 100)

    p_feat = doc.add_paragraph()
    p_feat.paragraph_format.space_before = Pt(4)
    p_feat.paragraph_format.space_after = Pt(2)
    p_feat.add_run("Cambodia-Specific Market Features:").font.bold = True

    market_features = [
        ("5 Core Baskets: ", "We model the 5 high-velocity categories (~81.6% of Cambodia's basket): Food (44.8%), Housing/Utilities (17.1%), Transport (12.2%), Restaurants (3.1%), and Alcohol (1.6%)."),
        ("Freight Spillover: ", "Fuel price momentum (Transport) is selectively fed into Food and Restaurant catering to model logistics cost pass-through."),
        ("Holiday Handling: ", "We built an exponential decay kernel for Khmer holidays (Khmer New Year, Pchum Ben, Water Festival) so temporary ceremonial spikes are not misread as permanent inflation."),
        ("FX Pass-Through: ", "Ingests daily USD/KHR commercial exchange rates.")
    ]
    for ft, fd in market_features:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(ft).font.bold = True
        p.add_run(fd)

    # Convergence plot
    conv_path = os.path.join(os.path.dirname(__file__), "..", "thesis", "images", "cpi_nowcasting_convergence.png")
    if os.path.exists(conv_path):
        p_conv = doc.add_paragraph()
        p_conv.paragraph_format.space_before = Pt(6)
        p_conv.paragraph_format.space_after = Pt(2)
        p_conv.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_conv.add_run().add_picture(conv_path, width=Inches(5.6))
        
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_before = Pt(1)
        p_cap.paragraph_format.space_after = Pt(6)
        r_cap = p_cap.add_run("Figure 3: Intra-Month Nowcasting Convergence with Monotonically Decaying Error Bounds")
        r_cap.font.name = "Calibri"
        r_cap.font.size = Pt(8.5)
        r_cap.font.italic = True
        r_cap.font.color.rgb = RGBColor(100, 100, 100)

    # ── 5. METABASE MONITORING & DASHBOARDS ───────────────────────────────────
    h5 = doc.add_heading("5. Decision-Support Metabase Dashboards & Monitoring", level=1)
    h5.paragraph_format.space_before = Pt(10)
    h5.paragraph_format.space_after = Pt(4)

    doc.add_paragraph(
        "To provide actionable macroeconomic intelligence and continuous pipeline observability, the system "
        "implements three dedicated production dashboards in Metabase (running in Docker containers):"
    )

    dashboards = [
        ("Dashboard 1: Macro CPI & Inflation Analytics",
         "Shows daily Headline CPI and Core CPI (which removes volatile food and fuel prices), monthly inflation rates, and price changes across all 12 consumption categories compared against official government reports.",
         "dashboard_97_macro_cpi.png",
         "Figure 4: Metabase Dashboard 1 — Real-Time Macro CPI & Inflation Analytics"),

        ("Dashboard 2: Operations & Data Source Telemetry",
         "Tracks the daily health of our scrapers across all 11 sources. It shows how many product prices were collected each day, scraping speed, and website connection status.",
         "dashboard_98_telemetry.png",
         "Figure 5: Metabase Dashboard 2 — Data Lake Operations & Scraping Telemetry"),

        ("Dashboard 3: Silver Layer Data Quality Screener",
         "Checks the cleanliness of our data every day. It tracks product size standardization (converting items to 1kg or 1L), USD to Khmer Riel currency conversion, product matching across stores, and AI classification accuracy.",
         "dashboard_99_silver_quality.png",
         "Figure 6: Metabase Dashboard 3 — Silver Layer Data Quality & Classification Screener")
    ]

    for title, desc, img_file, caption in dashboards:
        doc.add_heading(title, level=2)
        p_desc = doc.add_paragraph(desc)
        p_desc.paragraph_format.space_before = Pt(1)
        p_desc.paragraph_format.space_after = Pt(4)

        img_path = os.path.join(os.path.dirname(__file__), "..", "thesis", "images", img_file)
        if os.path.exists(img_path):
            p_img = doc.add_paragraph()
            p_img.paragraph_format.space_before = Pt(4)
            p_img.paragraph_format.space_after = Pt(2)
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_img.add_run().add_picture(img_path, width=Inches(5.8))

            p_cap = doc.add_paragraph()
            p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_cap.paragraph_format.space_before = Pt(1)
            p_cap.paragraph_format.space_after = Pt(6)
            r_cap = p_cap.add_run(caption)
            r_cap.font.name = "Calibri"
            r_cap.font.size = Pt(8.5)
            r_cap.font.italic = True
            r_cap.font.color.rgb = RGBColor(100, 100, 100)

    try:
        doc.save(filename)
        print(f"Document successfully created: {filename}")
    except PermissionError:
        fallback = filename.replace(".docx", "_v2.docx")
        doc.save(fallback)
        print(f"Original file was open in Word. Saved to: {fallback}")

if __name__ == "__main__":
    out_file = "Nowcasting_Inflation_via_Daily_Web_Scraping_Price.docx"
    build_docx(out_file)
