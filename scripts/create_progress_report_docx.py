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
    doc.add_paragraph("Protocols & Methods:").runs[0].font.bold = True
    scrape_methods = [
        ("REST / GraphQL APIs: ", "Reverse-proxy APIs for supermarkets (AEON, DeliShop) and marketplaces (L192)."),
        ("HTTP Requests with TLS Fingerprinting: ", "curl_cffi using Chrome TLS fingerprint impersonation to bypass anti-bot defenses."),
        ("Headless Playwright: ", "Dynamic browser escalation if Cloudflare or 403 Forbidden is met.")
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

    # Stage 3
    doc.add_heading("Stage 3: Silver Layer (Standardization, AI Classification & Quality Control)", level=2)
    p_s_table = doc.add_paragraph()
    p_s_table.paragraph_format.space_after = Pt(2)
    p_s_table.add_run("Database Table: ").font.bold = True
    p_s_table.add_run("silver.standardized_prices\n")
    p_s_table.add_run("The Silver Layer has 3 main jobs:\n")
    r_flow = p_s_table.add_run("[Raw Scrape] ──► 1. Clean Data ──► 2. Match Product ──► 3. Classify Basket ──► [Clean Silver Item]")
    r_flow.font.bold = True
    r_flow.font.color.rgb = NAVY

    doc.add_heading("1. Clean the Data (Standardize)", level=3)
    clean_points = [
        ("Removes noise: ", "Deletes marketing words (SALE, HOT DEAL, 50% OFF) and old price tags."),
        ("Normalizes units: ", "Converts volumes and weights into standard sizes (500ml, 1kg) to calculate price per liter/kg."),
        ("Handles dual currency: ", "Converts USD and Khmer Riel using the daily MEF exchange rate."),
        ("Fixes Khmer text: ", "Segments unspaced Khmer words and translates digits (០-៩ → 0-9).")
    ]
    for ct, cd in clean_points:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(ct).font.bold = True
        p.add_run(cd)

    doc.add_heading("2. Match the Product (Find the Same Item)", level=3)
    doc.add_paragraph("Connects identical products across different stores (e.g., AEON vs. DeliShop) using a 5-step waterfall:")
    match_steps = [
        ("Barcode (GTIN): ", "Exact match."),
        ("Store SKU: ", "Match with past days' catalog."),
        ("Clean Name & Size: ", "Exact text match with size protection (prevents 330ml matching 1.5L)."),
        ("AI Vector (pgvector): ", "Matches English and Khmer equivalents (≥95% similarity)."),
        ("Fuzzy Spelling: ", "Catches small typos.")
    ]
    for mt, md in match_steps:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(mt).font.bold = True
        p.add_run(md)

    doc.add_heading("3. Classify into Official Baskets (UN COICOP)", level=3)
    p_cl = doc.add_paragraph(style='List Bullet')
    p_cl.paragraph_format.space_before = Pt(1)
    p_cl.paragraph_format.space_after = Pt(2)
    p_cl.add_run("Uses Google Gemini AI in batches to assign the official 4-digit government code (e.g., 01.1.1 for Rice/Bread).")
    
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
        p.paragraph_format.space_after = Pt(2)
        p.add_run(gt).font.bold = True
        p.add_run(gd)

    doc.add_page_break()

    # The Gold Layer in Brief
    doc.add_heading("The Gold Layer in Brief: From Clean Products to Official CPI", level=2)
    p_g_desc = doc.add_paragraph()
    p_g_desc.paragraph_format.space_after = Pt(3)
    p_g_desc.add_run("The Gold Layer applies official international standards (ILO / UN guidelines) to turn thousands of clean daily prices into national economic indicators.\n")
    p_g_desc.add_run("It does this in 3 main steps:\n")
    r_gflow = p_g_desc.add_run("[Clean Silver Items] ──► 1. Jevons Index ──► 2. Laspeyres Aggregation ──► 3. Core CPI & Marts")
    r_gflow.font.bold = True
    r_gflow.font.color.rgb = NAVY

    doc.add_heading("1. Elementary Index Calculation (Jevons Formula)", level=3)
    p_jev = doc.add_paragraph(style='List Bullet')
    p_jev.paragraph_format.space_before = Pt(1)
    p_jev.paragraph_format.space_after = Pt(2)
    p_jev.add_run("(Jevons Geometric Mean): ").font.bold = True
    p_jev.add_run("Instead of a simple average (which gets distorted by expensive luxury items), the system uses the geometric mean:\n")
    r_eq1 = p_jev.add_run("I_rice,t = ( (P_1,t / P_1,0) × (P_2,t / P_2,0) × ... × (P_n,t / P_n,0) )^(1/n)")
    r_eq1.font.bold = True
    r_eq1.font.color.rgb = TEAL

    p_imp = doc.add_paragraph(style='List Bullet')
    p_imp.paragraph_format.space_before = Pt(1)
    p_imp.paragraph_format.space_after = Pt(2)
    p_imp.add_run("Missing Price Imputation: ").font.bold = True
    p_imp.add_run("If an item is temporarily out-of-stock, a 7-day carry-forward rule fills in the price so the index doesn't jump wildly.")

    doc.add_heading("2. Official National Aggregation (Laspeyres Formula)", level=3)
    doc.add_paragraph("Cambodians spend more money on food than on furniture. To reflect real life, the 12 COICOP divisions are combined using official government survey expenditure weights (CSES 2020):")
    p_lasp = doc.add_paragraph()
    p_lasp.paragraph_format.space_before = Pt(1)
    p_lasp.paragraph_format.space_after = Pt(2)
    r_eq2 = p_lasp.add_run("Headline CPI = ∑ ( Weight × Division Index )")
    r_eq2.font.bold = True
    r_eq2.font.color.rgb = TEAL

    lasp_weights = [
        ("Food & Drinks (01): ", "44.775% (Highest weight in Cambodia)"),
        ("Housing & Electricity (04): ", "17.062%"),
        ("Transport & Fuel (07): ", "12.203%"),
        ("All other 9 Divisions: ", "Remaining 25.960% (Clothing, Health, Telecom, etc.)")
    ]
    for lt, ld in lasp_weights:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(lt).font.bold = True
        p.add_run(ld)

    doc.add_heading("3. Central Bank Metric: Core CPI", level=3)
    doc.add_paragraph("For central bankers at the National Bank of Cambodia (NBC), temporary global oil spikes or seasonal vegetable floods distort the real picture:")
    p_core = doc.add_paragraph(style='List Bullet')
    p_core.paragraph_format.space_before = Pt(1)
    p_core.paragraph_format.space_after = Pt(2)
    p_core.add_run("Refined Core CPI: ").font.bold = True
    p_core.add_run("The system calculates a second official index that removes Food (01) and Energy (04):\n")
    r_eq3 = p_core.add_run("Core CPI = ( ∑_{ex-Food, ex-Energy} w_j · I_j ) / ( ∑ w_j )\n")
    r_eq3.font.bold = True
    r_eq3.font.color.rgb = TEAL
    p_core.add_run("This shows the underlying, long-term price stability of the economy.")

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

    doc.save(filename)
    print(f"Document successfully created: {filename}")

if __name__ == "__main__":
    build_docx()
