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
        hrun = hp.add_run("Cambodia Daily CPI Pipeline · Progress Report · GDDE / MEF & ITC")
        hrun.font.name = "Calibri"
        hrun.font.size = Pt(8.5)
        hrun.font.color.rgb = RGBColor(120, 120, 120)
        
        # Footer
        fp = section.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        frun = fp.add_run("Author: TAING Korngmeng (Data Science, AMS/ITC) | Host: General Dept. of Digital Economy (GDDE/MEF)")
        frun.font.name = "Calibri"
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = RGBColor(120, 120, 120)

    # ── Colors ────────────────────────────────────────────────────────────────
    NAVY = RGBColor(12, 44, 98)      # #0C2C62
    TEAL = RGBColor(20, 110, 120)    # #146E78
    EMERALD = RGBColor(25, 135, 84)  # #198754
    DARK = RGBColor(33, 37, 41)

    # ── Title & Subtitle ──────────────────────────────────────────────────────
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(2)
    r_title = p_title.add_run("Cambodia Daily Consumer Price Index (CPI) Pipeline")
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(19)
    r_title.font.bold = True
    r_title.font.color.rgb = NAVY

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(4)
    r_sub = p_sub.add_run("Automated Daily Price Intelligence & Machine Learning Inflation Nowcasting")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(11.5)
    r_sub.font.bold = True
    r_sub.font.color.rgb = TEAL

    p_meta = doc.add_paragraph()
    p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_meta.paragraph_format.space_before = Pt(0)
    p_meta.paragraph_format.space_after = Pt(8)
    r_meta = p_meta.add_run("Progress Report  |  Author: TAING Korngmeng  |  GDDE / MEF & ITC (AMS)  |  September 2026")
    r_meta.font.name = "Calibri"
    r_meta.font.size = Pt(9)
    r_meta.font.color.rgb = RGBColor(100, 100, 100)

    # ── Project Info Table ────────────────────────────────────────────────────
    meta_table = doc.add_table(rows=2, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.autofit = False
    
    col_widths = [Inches(3.6), Inches(3.6)]
    cells_flat = [
        ("Project: ", "Cambodia Daily CPI Medallion Pipeline", "Status: ", "100% Operational & Live in Production"),
        ("Host Agency: ", "General Dept. of Digital Economy (GDDE / MEF)", "Institution: ", "Institute of Technology of Cambodia (ITC / AMS)"),
    ]

    for row_idx, data in enumerate(cells_flat):
        cell_l = meta_table.cell(row_idx, 0)
        cell_r = meta_table.cell(row_idx, 1)
        cell_l.width = col_widths[0]
        cell_r.width = col_widths[1]
        set_cell_background(cell_l, "F4F6F9")
        set_cell_background(cell_r, "F4F6F9")
        set_cell_margins(cell_l, top=40, bottom=40, left=80, right=80)
        set_cell_margins(cell_r, top=40, bottom=40, left=80, right=80)

        p1 = cell_l.paragraphs[0]
        p1.paragraph_format.space_after = Pt(0)
        r1a = p1.add_run(data[0])
        r1a.font.bold = True
        r1a.font.size = Pt(8.5)
        r1b = p1.add_run(data[1])
        r1b.font.size = Pt(8.5)

        p2 = cell_r.paragraphs[0]
        p2.paragraph_format.space_after = Pt(0)
        r2a = p2.add_run(data[2])
        r2a.font.bold = True
        r2a.font.size = Pt(8.5)
        r2b = p2.add_run(data[3])
        r2b.font.size = Pt(8.5)
        if "100%" in data[3]:
            r2b.font.bold = True
            r2b.font.color.rgb = EMERALD

    set_table_borders(meta_table, color="D0D5DD")

    p_sp = doc.add_paragraph()
    p_sp.paragraph_format.space_before = Pt(4)
    p_sp.paragraph_format.space_after = Pt(4)

    # ── KPI Cards Table ───────────────────────────────────────────────────────
    kpi_table = doc.add_table(rows=1, cols=3)
    kpi_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    kpi_cols = [Inches(2.4), Inches(2.4), Inches(2.4)]

    kpi_contents = [
        ("DAILY COLLECTION", "35,792", "Daily Quotes Ingested", "• 1,273,000+ total prices\n• 25 endpoints covered\n• 99.3% daily reliability", "0C2C62"),
        ("AI PRODUCT SORTING", "99.04%", "Catalog Categorization", "• 50,303 items tracked\n• 0 category code mismatches\n• 12/12 UN divisions", "198754"),
        ("NOWCASTING ACCURACY", "±0.0181 pp", "vs Official NIS Release", "• NIS Official: +0.3470%\n• Pipeline Nowcast: +0.3651%\n• MAE: 0.12 index pts", "0C2C62")
    ]

    for idx, (title, big, sub, bullets, color_hex) in enumerate(kpi_contents):
        cell = kpi_table.cell(0, idx)
        cell.width = kpi_cols[idx]
        set_cell_background(cell, "FFFFFF")
        set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
        
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(1)
        r_title = p.add_run(title + "\n")
        r_title.font.name = "Calibri"
        r_title.font.size = Pt(8)
        r_title.font.bold = True
        r_title.font.color.rgb = NAVY

        r_big = p.add_run(big + "\n")
        r_big.font.name = "Calibri"
        r_big.font.size = Pt(15)
        r_big.font.bold = True
        r_big.font.color.rgb = EMERALD if color_hex == "198754" else NAVY

        r_sub = p.add_run(sub + "\n\n")
        r_sub.font.name = "Calibri"
        r_sub.font.size = Pt(8)
        r_sub.font.color.rgb = RGBColor(100, 100, 100)

        r_bul = p.add_run(bullets)
        r_bul.font.name = "Calibri"
        r_bul.font.size = Pt(8)
        r_bul.font.color.rgb = DARK

    set_table_borders(kpi_table, color="B8C4D4")

    # ── SECTION 1: SPECIFIC OBJECTIVES ONLY ───────────────────────────────────
    h1 = doc.add_heading("1. Specific Objectives", level=1)
    h1.paragraph_format.space_before = Pt(12)
    h1.paragraph_format.space_after = Pt(4)

    p_intro = doc.add_paragraph()
    p_intro.paragraph_format.space_after = Pt(4)
    p_intro.add_run("The project addresses three specific objectives (from Thesis Chapter I):")

    obj_items = [
        ("Objective 1 — Automated Daily Price Collection & Monitoring: ", 
         "Build an automated data pipeline that collects and stores consumer price data every morning at 08:00 AM across 25 retail, utility, transport, and government sources in Phnom Penh, with built-in quality checks."),
        ("Objective 2 — Price Index Compilation & Inflation Nowcasting: ", 
         "Apply standard economic formulas (geometric Jevons index) to compute daily price changes without mathematical drift, and use machine learning (Ridge regression) to nowcast month-end inflation early."),
        ("Objective 3 — Interactive Decision-Support Dashboards: ", 
         "Develop interactive dashboards in Metabase and Power BI to give government analysts real-time visibility into daily price trends, category breakdowns, and inflation nowcasts.")
    ]

    for title, text in obj_items:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(title)
        r.font.bold = True
        r.font.color.rgb = NAVY
        p.add_run(text)

    # ── SECTION 2: PROJECT METHODOLOGY ────────────────────────────────────────
    h2 = doc.add_heading("2. Project Methodology (The Five Core Pillars)", level=1)
    h2.paragraph_format.space_before = Pt(10)
    h2.paragraph_format.space_after = Pt(4)

    pillars = [
        ("Pillar 1: Multi-Source Daily Collection", "Automated scrapers collect over 35,000 prices every morning at 08:00 AM from 25 websites, APIs, and official gazettes across Phnom Penh."),
        ("Pillar 2: Cleaning & Product Tracking", "Standardizes text, converts US Dollar prices into Cambodian Riel using daily official exchange rates, and tracks the exact same item from day to day."),
        ("Pillar 3: Smart Categorization", "Assigns every item into official United Nations COICOP consumer groups using fast store rules and Google Gemini AI, saving results permanently in the database."),
        ("Pillar 4: Fair Index Calculation", "Averages price changes using the geometric Jevons formula to eliminate formula bias (+1.18% annual drift), and balances stores so large supermarket catalogs do not overpower smaller grocers."),
        ("Pillar 5: Real-Time Inflation Nowcasting", "Uses early-month price speed in food, fuel, and exchange rates to nowcast month-end inflation with uncertainty bands that shrink toward zero as the month completes.")
    ]

    for title, desc in pillars:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(f"{title}: ")
        r.font.bold = True
        p.add_run(desc)

    doc.add_page_break()

    # ── SECTION 3: SYSTEM ARCHITECTURE & BRONZE LAYER ─────────────────────────
    h3 = doc.add_heading("3. System Architecture & Bronze Layer (Raw Collection)", level=1)
    h3.paragraph_format.space_before = Pt(0)
    h3.paragraph_format.space_after = Pt(4)

    p_arch = doc.add_paragraph()
    p_arch.paragraph_format.space_after = Pt(4)
    p_arch.add_run("The pipeline uses a 3-step ")
    p_arch.add_run("Medallion Architecture").font.bold = True
    p_arch.add_run(" (Bronze → Silver → Gold) hosted on PostgreSQL 16:")

    med_steps = [
        ("Bronze Layer (Raw Storage): ", "Stores exact, untouched copies of original store listings, recording scrape timestamps and source identifiers for complete data lineage."),
        ("Silver Layer (Data Cleaning & AI Sorting): ", "Cleans text, converts USD to Cambodian Riel, extracts standard units (kg/L) to detect shrinkflation, and classifies items into official categories."),
        ("Gold Layer (Final Analytics & Nowcasting): ", "Calculates store-balanced price indexes, applies CSES 2023 national household weights, and runs machine learning inflation nowcasting.")
    ]
    for m_title, m_desc in med_steps:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(m_title).font.bold = True
        p.add_run(m_desc)

    # Image
    img_path = r"D:\CPI PIPELINE\thesis\images\cpi_architecture_clean.png"
    if os.path.exists(img_path):
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(4)
        p_img.paragraph_format.space_after = Pt(2)
        doc.add_picture(img_path, width=Inches(5.0))
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_after = Pt(4)
        r_c = p_cap.add_run("Figure 1: End-to-End System Architecture: From 25 Sources to Live Dashboards.")
        r_c.font.size = Pt(8)
        r_c.font.italic = True
        r_c.font.color.rgb = RGBColor(100, 100, 100)

    doc.add_heading("Bronze Layer: 25 Daily Data Sources Summary", level=2)
    
    src_data = [
        ("Supermarkets & Delivery (AEON 1 & 3, DeliShop, GrabMart Lucky & Chip Mong)", "01, 02, 05, 12", "REST API & JSON", "27,270", "99.2%"),
        ("E-Commerce Marketplaces (L192 Marketplace, Khmer24)", "03, 05, 09, 12", "GraphQL & Web", "9,350", "98.9%"),
        ("Pharmacies & Health (Community Pharmacy, GrabMart Ucare)", "06, 12", "PostgREST & JSON", "1,420", "99.7%"),
        ("Transport & Vehicles (redBus, BookMeBus, Khmer Moto Shop)", "07", "Search & REST API", "1,075", "99.5%"),
        ("Housing & Regulated Utilities (Khmer24, Realestate, EDC Power, PPWSA Water)", "04", "Web & Regulatory", "3,460", "98.0%"),
        ("Telecoms & Tech (Cellcard, Smart, Metfone, Ary Store, Samnang)", "08, 09", "API & Web", "1,845", "99.7%"),
        ("Fuel & Official Exchange (MOC Gazette, Tela Fuel, MEF Central Exchange Rate)", "04, 07, 12", "Telegram & Feed", "17", "100.0%"),
        ("Total 25 Endpoints Across All 12 UN Consumer Divisions", "01–12", "Automated Fleet", "35,792", "99.3%")
    ]

    stbl = doc.add_table(rows=len(src_data) + 1, cols=5)
    stbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    s_widths = [Inches(2.8), Inches(1.1), Inches(1.3), Inches(0.9), Inches(0.9)]
    s_headers = ["Market Sector & Sources", "Divisions", "Collection Method", "Daily Quotes", "Success Rate"]

    for col_idx, htext in enumerate(s_headers):
        cell = stbl.cell(0, col_idx)
        cell.width = s_widths[col_idx]
        set_cell_background(cell, "0C2C62")
        set_cell_margins(cell, top=40, bottom=40, left=60, right=60)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(htext)
        run.font.name = "Calibri"
        run.font.size = Pt(8)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, r_data in enumerate(src_data):
        is_tot = (row_idx == len(src_data) - 1)
        bg = "EAF0F8" if is_tot else ("F8F9FA" if row_idx % 2 == 1 else "FFFFFF")
        for col_idx, text in enumerate(r_data):
            cell = stbl.cell(row_idx + 1, col_idx)
            cell.width = s_widths[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=35, bottom=35, left=60, right=60)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(8)
            if is_tot:
                run.font.bold = True
                run.font.color.rgb = NAVY

    set_table_borders(stbl, color="D0D5DD")

    p_sc = doc.add_paragraph()
    p_sc.paragraph_format.space_before = Pt(4)
    p_sc.paragraph_format.space_after = Pt(2)
    p_sc.add_run("Bronze Safeguards: ").font.bold = True
    p_sc.add_run("Strict natural-key deduplication prevents double-recording on network retries. Automated circuit breakers pause downstream processing if daily quote volume drops by >30% or if prices jump abnormally after currency conversion.")

    doc.add_page_break()

    # ── SECTION 4: SILVER LAYER ───────────────────────────────────────────────
    h4 = doc.add_heading("4. Silver Layer (Data Cleaning & AI Sorting)", level=1)
    h4.paragraph_format.space_before = Pt(0)
    h4.paragraph_format.space_after = Pt(4)

    sil_bullets = [
        ("Currency Normalization to Riel: ", "Ingests daily official exchange rates from MEF and converts all USD prices into Cambodian Riel (KHR) before running statistical checks."),
        ("Catching Shrinkflation: ", "Extracts volume/weight from product titles to compute price per standard metric unit (KHR/kg or KHR/L). When package sizes decrease while the price tag stays constant, the unit price immediately catches the hidden inflation."),
        ("5-Step Matching Ladder: ", "Tracks identical products across days using barcodes, store SKUs, and text matching. Enforces strict physical safety guards so a 1-can soda never merges with a 24-can box, 128GB and 256GB phones never merge, and clothing sizes stay separate."),
        ("Two-Tier Classification: ", "Specialized single-sector stores (gas stations, pharmacies, buses, utilities) are sorted with 100% accuracy at zero cost (14.34% of items). Complex supermarket items are categorized in batches of 40 using Google Gemini 3.1 Flash Lite AI (76.42% of items)."),
        ("Database Memoization ('Sort Once, Remember Forever'): ", "Once an item is categorized, its category is permanently saved in PostgreSQL. Over 99.2% of daily items reuse their saved category in 0 milliseconds, keeping ongoing AI costs at $0.")
    ]

    for title, text in sil_bullets:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(title).font.bold = True
        p.add_run(text)

    doc.add_heading("Gemini AI Linguistic Disambiguation Examples", level=2)

    traps_data = [
        ("Bourbon Choco Chip Cookies", "'Bourbon' (Whiskey)", "02.1.1 (Alcohol / Spirits)", "01.1.8 (Bakery & Cookies)", "Correct"),
        ("Camel Salted Peanuts 150g", "'Camel' (Cigarette brand)", "02.2.0 (Tobacco Products)", "01.1.7 (Nuts & Snacks)", "Correct"),
        ("Apple iPhone 15 Pro 128GB", "'Apple' (Fresh fruit)", "01.1.6 (Fresh Fruits)", "08.2.0 (Mobile Smartphones)", "Correct"),
        ("Haidilao Hot Pot Soup Base", "Food item vs Appliance", "05.3.1 (Cooking Appliance)", "01.1.9 (Sauces & Seasonings)", "Correct"),
        ("Cleaning Vinegar Spray 500ml", "Cleaning vs Cooking Vinegar", "01.1.9 (Cooking Vinegar)", "05.6.1 (Cleaning Products)", "Correct")
    ]

    ttbl = doc.add_table(rows=len(traps_data) + 1, cols=5)
    ttbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    t_widths = [Inches(2.0), Inches(1.5), Inches(1.5), Inches(1.5), Inches(0.7)]
    t_headers = ["Product Listing Title", "Ambiguity / Word Trap", "Keyword Match", "Gemini 3.1 AI Decision", "Result"]

    for col_idx, htext in enumerate(t_headers):
        cell = ttbl.cell(0, col_idx)
        cell.width = t_widths[col_idx]
        set_cell_background(cell, "0C2C62")
        set_cell_margins(cell, top=40, bottom=40, left=60, right=60)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(htext)
        run.font.name = "Calibri"
        run.font.size = Pt(8)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, r_data in enumerate(traps_data):
        bg = "F8F9FA" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(r_data):
            cell = ttbl.cell(row_idx + 1, col_idx)
            cell.width = t_widths[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=35, bottom=35, left=60, right=60)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(8)
            if col_idx == 4:
                run.font.bold = True
                run.font.color.rgb = EMERALD

    set_table_borders(ttbl, color="D0D5DD")

    doc.add_page_break()

    # ── SECTION 5: GOLD LAYER ─────────────────────────────────────────────────
    h5 = doc.add_heading("5. Gold Layer (Index Calculation & Inflation Nowcasting)", level=1)
    h5.paragraph_format.space_before = Pt(0)
    h5.paragraph_format.space_after = Pt(4)

    gold_bullets = [
        ("Fair Price Averaging (Jevons Formula): ", "Standard arithmetic averages (Carli formula) drift upward by +1.18% per year because of sales bounces (-50% then +100% falsely registers as +25%). The pipeline uses the geometric Jevons formula in log space, where price rises and drops cancel out fairly with zero distortion."),
        ("Store Balancing: ", "Prevents a large hypermarket with 190 rice products from overpowering a smaller store with 10 rice products. The pipeline calculates index changes inside each store first, then combines stores with equal weight so catalog size never distorts the price signal."),
        ("National Spending Weights (CSES 2023): ", "Elementary indexes are rolled up across 76 real-world spending categories weighted by official household survey data: Food & Drinks (44.78%), Housing & Utilities (17.08%), Transport (12.18%), and all other goods (25.96%)."),
        ("Headline vs. Core CPI: ", "Headline CPI tracks all consumer goods (+0.28% in 30 days). Refined Core CPI removes volatile fresh food and fuel (+0.07% in 30 days), confirming to policymakers that underlying monetary inflation remained stable."),
        ("Machine Learning Inflation Nowcasting: ", "A two-stage regularized Ridge nowcaster monitors high-frequency price velocity across food, fuel, utility tariffs, and USD/KHR exchange rates during early days of the month to nowcast the final month-end inflation rate. Uncertainty bands shrink toward zero as the month completes.")
    ]

    for title, text in gold_bullets:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(3)
        p.add_run(title).font.bold = True
        p.add_run(text)

    # ── SECTION 6: RESULTS, SOLVED PROBLEMS & NEXT MILESTONES ─────────────────
    h6 = doc.add_heading("6. Results, Solved Problems & Next Milestones", level=1)
    h6.paragraph_format.space_before = Pt(10)
    h6.paragraph_format.space_after = Pt(4)

    doc.add_heading("Comparison with Official Government Data (August 2026 Validation)", level=2)

    bench_data = [
        ("National Headline CPI (All Goods)", "100.000%", "+0.3470%", "+0.3651%", "+0.0181 pp", "High Precision Match (MAE 0.12 pts)"),
        ("Division 01: Food & Drinks", "44.775%", "+0.5120%", "+0.4821%", "-0.0299 pp", "Accurately tracks fresh produce trend"),
        ("Division 04: Housing, Water, Electricity", "17.084%", "+0.0150%", "+0.0215%", "+0.0065 pp", "Anchored by official utility rates"),
        ("Division 07: Transport (Fuel & Buses)", "12.180%", "+0.7100%", "+0.7410%", "+0.0310 pp", "Matches official fuel price cap updates"),
        ("Refined Core Basket (Excl. Food & Fuel)", "52.200%", "-0.0580%", "-0.0700%", "-0.0120 pp", "Confirms stable underlying direction")
    ]

    btbl = doc.add_table(rows=len(bench_data) + 1, cols=6)
    btbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    b_widths = [Inches(2.1), Inches(0.9), Inches(1.0), Inches(1.0), Inches(0.9), Inches(1.3)]
    b_headers = ["Consumer Spending Group", "CSES Weight", "Official NIS", "Pipeline Nowcast", "Difference", "Verification Status"]

    for col_idx, htext in enumerate(b_headers):
        cell = btbl.cell(0, col_idx)
        cell.width = b_widths[col_idx]
        set_cell_background(cell, "0C2C62")
        set_cell_margins(cell, top=40, bottom=40, left=60, right=60)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(htext)
        run.font.name = "Calibri"
        run.font.size = Pt(8)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, r_data in enumerate(bench_data):
        is_hl = (row_idx == 0)
        bg = "EAF0F8" if is_hl else ("F8F9FA" if row_idx % 2 == 1 else "FFFFFF")
        for col_idx, text in enumerate(r_data):
            cell = btbl.cell(row_idx + 1, col_idx)
            cell.width = b_widths[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=35, bottom=35, left=60, right=60)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(8)
            if is_hl:
                run.font.bold = True
                if col_idx in [0, 4]:
                    run.font.color.rgb = NAVY

    set_table_borders(btbl, color="D0D5DD")

    p_bi = doc.add_paragraph()
    p_bi.paragraph_format.space_before = Pt(4)
    p_bi.paragraph_format.space_after = Pt(4)
    p_bi.add_run("Interactive Dashboards: ").font.bold = True
    p_bi.add_run("3 interactive Metabase and Power BI dashboards allow analysts to inspect daily inflation trends, division breakdowns, individual stores, and collection telemetry.")

    doc.add_heading("Difficult Problems Encountered and Practical Solutions", level=2)
    prob_data = [
        ("Slow Daily Startup", "Loading 25 scrapers took 100s every morning.", "Separated lightweight store manifests, cutting parse time to 1.04s."),
        ("Dual-Currency Swings", "Mixed USD/KHR prices caused false volatility alarms.", "Converted prices to Riel first using official central bank exchange rates."),
        ("Package Downsizing", "Downsized packages look cheaper if weight isn't tracked.", "Standardized to price per metric unit (kg/L) to detect shrinkflation."),
        ("AI Rate Limits & Costs", "Classifying 50,000 items individually caused 429 errors.", "Grouped 40 items per call and permanently cached results in PostgreSQL."),
        ("Upward Formula Drift", "Standard averages drift upward by +1.18% per year.", "Used geometric Jevons formula in log space to eliminate mathematical drift.")
    ]

    ptbl = doc.add_table(rows=len(prob_data) + 1, cols=3)
    ptbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    pr_widths = [Inches(1.8), Inches(2.4), Inches(3.0)]
    pr_headers = ["Challenge Encountered", "Why It Was a Problem", "Practical Solution"]

    for col_idx, htext in enumerate(pr_headers):
        cell = ptbl.cell(0, col_idx)
        cell.width = pr_widths[col_idx]
        set_cell_background(cell, "0C2C62")
        set_cell_margins(cell, top=40, bottom=40, left=60, right=60)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(htext)
        run.font.name = "Calibri"
        run.font.size = Pt(8)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, r_data in enumerate(prob_data):
        bg = "F8F9FA" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(r_data):
            cell = ptbl.cell(row_idx + 1, col_idx)
            cell.width = pr_widths[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=35, bottom=35, left=60, right=60)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(8)
            if col_idx == 0:
                run.font.bold = True

    set_table_borders(ptbl, color="D0D5DD")

    doc.add_heading("Next Project Milestones", level=2)
    mile_data = [
        ("M1: Defense Rehearsal", "September 2026", "Candidate & Academic Advisor", "Completed", "Rehearsal of 20-slide thesis presentation deck."),
        ("M2: Graduation Defense", "September 2026", "Examination Committee (ITC)", "Confirmed", "Official thesis defense for Degree in Applied Mathematics."),
        ("M3: Library Archival", "October 2026", "Academic Department / Library", "Scheduled", "Submission of signed 75-page thesis and code repository."),
        ("M4: System Handover", "October 2026", "GDDE / MEF Technical Team", "In Progress", "Delivery of Docker containers, operational scripts, and documentation.")
    ]

    mtbl = doc.add_table(rows=len(mile_data) + 1, cols=5)
    mtbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    m_widths = [Inches(1.6), Inches(1.1), Inches(1.7), Inches(0.9), Inches(1.9)]
    m_headers = ["Milestone", "Target Date", "Responsible Party", "Status", "Scope of Milestone"]

    for col_idx, htext in enumerate(m_headers):
        cell = mtbl.cell(0, col_idx)
        cell.width = m_widths[col_idx]
        set_cell_background(cell, "0C2C62")
        set_cell_margins(cell, top=40, bottom=40, left=60, right=60)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(htext)
        run.font.name = "Calibri"
        run.font.size = Pt(8)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, r_data in enumerate(mile_data):
        bg = "F8F9FA" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(r_data):
            cell = mtbl.cell(row_idx + 1, col_idx)
            cell.width = m_widths[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=35, bottom=35, left=60, right=60)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(8)
            if col_idx == 0:
                run.font.bold = True
            if col_idx == 3 and text in ["Completed", "Confirmed"]:
                run.font.bold = True
                run.font.color.rgb = EMERALD

    set_table_borders(mtbl, color="D0D5DD")

    doc.save(filename)
    print(f"Document successfully created: {filename}")

if __name__ == "__main__":
    build_docx()
