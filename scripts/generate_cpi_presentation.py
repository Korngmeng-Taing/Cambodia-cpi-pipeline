"""
Generate 13-slide Presentation Deck in PowerPoint (.pptx)
for Cambodia Daily Consumer Price Index (CPI) & Inflation Nowcasting.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_deck(output_path="presentation_cpi_methodology.pptx"):
    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9 widescreen
    prs.slide_height = Inches(7.5)

    # Color Palette
    NAVY = RGBColor(26, 54, 93)      # #1A365D Primary Dark
    SLATE = RGBColor(45, 55, 72)     # #2D3748 Body text
    BLUE = RGBColor(49, 130, 206)    # #3182CE Accent Blue
    LIGHT_BG = RGBColor(247, 250, 252) # #F7FAFC Card Background
    WHITE = RGBColor(255, 255, 255)
    TEAL = RGBColor(49, 151, 149)    # #319795 Success/Highlight
    GRAY_BORDER = RGBColor(226, 232, 240)

    blank_layout = prs.slide_layouts[6]

    def add_header(slide, title, subtitle):
        # Top banner
        header_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.733), Inches(1.1))
        tf = header_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(24)
        p.font.bold = True
        p.font.color.rgb = NAVY
        
        p2 = tf.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(13)
        p2.font.color.rgb = BLUE
        p2.space_before = Pt(4)

    def add_card(slide, left, top, width, height, bg_color=LIGHT_BG, border_color=GRAY_BORDER):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = bg_color
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1)
        return shape

    # ==========================================
    # SLIDE 1: Title & Executive Summary
    # ==========================================
    s1 = prs.slides.add_slide(blank_layout)
    # Background card
    bg = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()

    # Title box
    tb = s1.shapes.add_textbox(Inches(1.0), Inches(1.5), Inches(11.333), Inches(2.2))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "Autonomous Daily Consumer Price Index & Inflation Nowcasting for Cambodia"
    p.font.size = Pt(32)
    p.font.bold = True
    p.font.color.rgb = WHITE
    
    p2 = tf.add_paragraph()
    p2.text = "High-Frequency Alternative Economic Sensing via Multilingual Web Scraping & Econometric Machine Learning"
    p2.font.size = Pt(16)
    p2.font.color.rgb = RGBColor(190, 227, 248)
    p2.space_before = Pt(10)

    # 3 Stat Cards on Title Slide
    cards_data = [
        ("⚡ High Frequency", "Daily automated price scrapes across 30+ merchants and open utility gazettes (08:00 ICT)"),
        ("🎯 High Accuracy", "+0.52 Store-Balanced bias correction; 98.83% national consumption basket weight"),
        ("🏛️ Statistical Compliance", "Strict adherence to UN COICOP 2018 and official NIS Cambodia CSES Laspeyres weights")
    ]
    for i, (title, desc) in enumerate(cards_data):
        c_left = Inches(1.0 + i * 3.9)
        c_shape = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, c_left, Inches(4.2), Inches(3.6), Inches(2.0))
        c_shape.fill.solid()
        c_shape.fill.fore_color.rgb = RGBColor(44, 82, 130)
        c_shape.line.color.rgb = RGBColor(99, 179, 237)
        c_shape.line.width = Pt(1.5)
        
        c_tf = c_shape.text_frame
        c_tf.word_wrap = True
        c_tf.margin_left = c_tf.margin_right = Inches(0.2)
        c_tf.margin_top = Inches(0.2)
        cp1 = c_tf.paragraphs[0]
        cp1.text = title
        cp1.font.size = Pt(16)
        cp1.font.bold = True
        cp1.font.color.rgb = WHITE
        
        cp2 = c_tf.add_paragraph()
        cp2.text = desc
        cp2.font.size = Pt(11)
        cp2.font.color.rgb = RGBColor(226, 232, 240)
        cp2.space_before = Pt(6)

    s1.notes_slide.notes_text_frame.text = (
        "Good morning committee members. Traditional official CPI in Cambodia is published once a month with a "
        "30-to-60 day publication lag. Today, we present an end-to-end, high-frequency price intelligence pipeline "
        "that crawls over 30 retail and utility sources daily, applies machine learning entity resolution, computes an "
        "axiomatic Jevons Elementary Aggregate Index, and delivers real-time inflation nowcasting with official statistical compliance."
    )

    # ==========================================
    # SLIDE 2: The Macroeconomic Information Asymmetry
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "The Macroeconomic Information Asymmetry", 
               "Why traditional retrospective surveys need digital high-frequency complements")

    # Table comparing Traditional vs Digital
    table_shape = s2.shapes.add_table(6, 3, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.8))
    table = table_shape.table
    table.columns[0].width = Inches(3.0)
    table.columns[1].width = Inches(4.366)
    table.columns[2].width = Inches(4.366)

    headers = ["Dimension", "Traditional Official CPI (NIS Cambodia)", "Digital High-Frequency Pipeline (Our System)"]
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        p = cell.text_frame.paragraphs[0]
        p.text = h
        p.font.bold = True
        p.font.size = Pt(12)
        p.font.color.rgb = WHITE

    rows_data = [
        ("Observation Frequency", "Monthly clipboard market visits", "Daily automated crawling (08:00 ICT)"),
        ("Reporting Latency", "30 to 60 days lag", "Real-time (0-day lag) with dynamic nowcasts"),
        ("Sample Size", "~400–600 fixed commodities", "50,300+ tracked canonical SKUs (16,600+ daily quotes)"),
        ("Data Integrity", "Manual paper & spreadsheet entry", "Immutable Bronze Lakehouse + Automated Audit Trail"),
        ("Granularity", "National & provincial monthly averages", "Daily store-level, 5-digit subclass, and division series")
    ]
    for i, row in enumerate(rows_data):
        for j, val in enumerate(row):
            cell = table.cell(i+1, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 == 0 else LIGHT_BG
            p = cell.text_frame.paragraphs[0]
            p.text = val
            p.font.size = Pt(11)
            p.font.color.rgb = NAVY if j == 2 else SLATE
            if j == 2:
                p.font.bold = True

    s2.notes_slide.notes_text_frame.text = (
        "Central banks and economic ministries cannot wait two months to discover that food or fuel prices have spiked. "
        "By capturing daily online retail quotes, our system eliminates reporting lag while adhering to the same national "
        "weighting structure used by the National Institute of Statistics."
    )

    # ==========================================
    # SLIDE 3: 5-Pillar Methodological Architecture
    # ==========================================
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "System Architecture: The Five Methodological Pillars",
               "From raw uncurated web payloads to publication-grade inflation metrics")

    pillars = [
        ("Pillar 1: Normalization", "Khmer Unicode cleaning, USD/KHR daily conversion, metric volume standardization to prevent shrinkflation bias."),
        ("Pillar 2: Entity Ladder", "5-level matching ladder (GTIN-13, SKU, Normalized Lexical, Vector embeddings with deterministic spec guards)."),
        ("Pillar 3: Classification", "Store Purity Locks + Gemini 3.1 Flash Lite micro-batch classification into UN COICOP 2018 subclasses."),
        ("Pillar 4: Index Engine", "Two-Stage Store-Balanced Jevons elementary index aggregation followed by Laspeyres CSES macroeconomic weighting."),
        ("Pillar 5: Nowcasting & Telemetry", "Two-Stage Regularized RidgeCV nowcasting with empirical Bayesian shrinkage and daily data quality observability.")
    ]
    for i, (p_title, p_desc) in enumerate(pillars):
        top_pos = Inches(1.8 + i * 1.05)
        c = add_card(s3, Inches(0.8), top_pos, Inches(11.733), Inches(0.95))
        tf = c.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.3)
        tf.margin_top = Inches(0.12)
        p1 = tf.paragraphs[0]
        p1.text = p_title
        p1.font.bold = True
        p1.font.size = Pt(13)
        p1.font.color.rgb = NAVY
        
        p2 = tf.add_paragraph()
        p2.text = p_desc
        p2.font.size = Pt(10.5)
        p2.font.color.rgb = SLATE
        p2.space_before = Pt(2)

    # ==========================================
    # SLIDE 4: Pillar 1 — Data Cleaning & Dimension Normalization
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "Pillar 1: Data Normalization & Defeating Shrinkflation",
               "Enforcing pure-price dimensional comparison across packaging shifts")

    # Left card: Normalization
    c_l = add_card(s4, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8))
    tf_l = c_l.text_frame
    tf_l.word_wrap = True
    tf_l.margin_left = tf_l.margin_right = Inches(0.3)
    tf_l.margin_top = Inches(0.2)
    p = tf_l.paragraphs[0]
    p.text = "Core Normalization Disciplines"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = NAVY

    bullets_l = [
        "Khmer Unicode Sanitization: Replaces Khmer numerals (០-៩) with standard digits (0-9) and strips promotional flags ('[BUY 1 GET 1]', 'PROMO').",
        "Dual-Currency Normalization: Real-time conversion of USD-denominated listings to Cambodian Riel (KHR) via MEF/NBC official daily FX rates.",
        "Consumable Metric Isolation: Strict dimensional parsing restricted to food, beverage, and personal care (Divisions 01, 02, 05, 06, 12). Non-consumable specifications (e.g. 5G/256GB in electronics) are insulated from weight parsing."
    ]
    for b in bullets_l:
        p = tf_l.add_paragraph()
        p.text = "• " + b
        p.font.size = Pt(11)
        p.font.color.rgb = SLATE
        p.space_before = Pt(12)

    # Right card: Shrinkflation Shield
    c_r = add_card(s4, Inches(6.8), Inches(1.8), Inches(5.733), Inches(4.8))
    tf_r = c_r.text_frame
    tf_r.word_wrap = True
    tf_r.margin_left = tf_r.margin_right = Inches(0.3)
    tf_r.margin_top = Inches(0.2)
    p = tf_r.paragraphs[0]
    p.text = "The Shrinkflation Shield in Practice"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = TEAL

    p_f = tf_r.add_paragraph()
    p_f.text = "Standardized Unit Price Formula:\nPrice_unit = Shelf Price (KHR) / Normalized Volume (kg or L)"
    p_f.font.bold = True
    p_f.font.size = Pt(12)
    p_f.font.color.rgb = NAVY
    p_f.space_before = Pt(10)

    bullets_r = [
        "Case Study: Milk Packaging Reduction",
        "Base Period: 1.0 Liter carton = 8,000 KHR (Unit price: 8,000 KHR/L).",
        "Current Period: Package downsized to 0.9 Liters while shelf price remains 8,000 KHR.",
        "Naive Shelf Comparison: 8,000 / 8,000 = 1.00 (Registers 0.0% inflation).",
        "Pipeline Pure-Price Comparison: 8,889 KHR/L / 8,000 KHR/L = 1.1111 (Accurately registers +11.1% inflation surge).",
        "Protects monetary statistics against disguised corporate price hikes."
    ]
    for b in bullets_r:
        p = tf_r.add_paragraph()
        p.text = "• " + b
        p.font.size = Pt(11)
        p.font.color.rgb = SLATE
        p.space_before = Pt(8)

    # ==========================================
    # SLIDE 5: Pillar 2 — The Five-Level Entity Matching Ladder
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "Pillar 2: Longitudinal Entity Resolution",
               "How we track the exact same product over time across different stores")

    levels = [
        ("Level 1: GTIN-13 Barcode Alias", "Deterministic exact barcode lookup. Pre-indexed GTIN catalog handles vendor packaging updates with 100% precision."),
        ("Level 2: In-Memory Store SKU Index", "Sub-millisecond hash map matching (<0.1ms). Re-identifies recurring catalog listings within the same retailer."),
        ("Level 3: Normalized Text + Size Tolerance", "Direct lexical matching combining normalized titles and strict metric quantity limits (<=10% variance)."),
        ("Level 4: Multilingual Vector + Spec Guard", "paraphrase-multilingual-mpnet embeddings (S_cos >= 0.80) coupled with deterministic physical specification guards."),
        ("Level 5: Genuinely New Product Enrolment", "Enrolled into gold.dim_item_base_prices with shadow tracking on Day t and active relative comparison on Day t+1.")
    ]
    for i, (l_title, l_desc) in enumerate(levels):
        top_pos = Inches(1.8 + i * 1.05)
        c = add_card(s5, Inches(0.8), top_pos, Inches(11.733), Inches(0.95))
        tf = c.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.3)
        tf.margin_top = Inches(0.12)
        p1 = tf.paragraphs[0]
        p1.text = l_title
        p1.font.bold = True
        p1.font.size = Pt(13)
        p1.font.color.rgb = NAVY
        
        p2 = tf.add_paragraph()
        p2.text = l_desc
        p2.font.size = Pt(10.5)
        p2.font.color.rgb = SLATE
        p2.space_before = Pt(2)

    s5.notes_slide.notes_text_frame.text = (
        "Semantic AI vector models are naturally 'number blind'—they think a 1-can and 24-can pack of soda are identical "
        "because the words are similar. Our Level 4 enforces a deterministic physical spec guard firewall that strictly separates "
        "different pack sizes and hardware specs before any cosine similarity is evaluated."
    )

    # ==========================================
    # SLIDE 6: Pillar 3 — Product Replacement & Quality Adjustment
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "Pillar 3: Product Discontinuation & Quality Adjustment",
               "Distinguishing pure monetary price movements from technological upgrades")

    types_data = [
        ("QUANTITY_ADJUSTED", "Package Resizing / Downsizing", 
         "When packaging changes for the same brand and product line, base prices are rescaled by the volume ratio (Volume_new / Volume_old). Prevents false artificial price jumps or drops."),
        ("HEDONIC_ADJUSTED", "Technological Feature Upgrades (Div 08/09)", 
         "Deploys time-dummy log-linear hedonic regression across consumer hardware (smartphones, laptops). Isolates attribute shadow prices (e.g. +18.2% storage premium, +4.6% RAM premium) to compute constant-utility prices."),
        ("DIRECT_EQUIVALENT", "Identical Packaging & Same Quality Tier", 
         "Direct 1:1 replacement when brand, formulation, and specification are verified identical. Splice factor = 1.0.")
    ]
    for i, (t_name, t_sub, t_desc) in enumerate(types_data):
        top_pos = Inches(1.8 + i * 1.55)
        c = add_card(s6, Inches(0.8), top_pos, Inches(11.733), Inches(1.35))
        tf = c.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.3)
        tf.margin_top = Inches(0.15)
        p1 = tf.paragraphs[0]
        p1.text = f"{t_name} — {t_sub}"
        p1.font.bold = True
        p1.font.size = Pt(13)
        p1.font.color.rgb = NAVY
        
        p2 = tf.add_paragraph()
        p2.text = t_desc
        p2.font.size = Pt(11)
        p2.font.color.rgb = SLATE
        p2.space_before = Pt(4)

    # Footnote card on audit table
    c_bot = add_card(s6, Inches(0.8), Inches(6.3), Inches(11.733), Inches(0.6), bg_color=WHITE, border_color=BLUE)
    tf_b = c_bot.text_frame
    p = tf_b.paragraphs[0]
    p.text = "Audit Integrity: Every product replacement is permanently audited in silver.dim_product_replacements with full lineage."
    p.font.size = Pt(10)
    p.font.color.rgb = BLUE
    p.font.bold = True

    # ==========================================
    # SLIDE 7: Pillar 4 — Defining the Elementary Aggregate
    # ==========================================
    s7 = prs.slides.add_slide(blank_layout)
    add_header(s7, "Pillar 4: Defining the Elementary Aggregate",
               "The bedrock of the CPI pyramid where product prices become category indices")

    # Comparison of formulas
    t_shape = s7.shapes.add_table(4, 4, Inches(0.8), Inches(1.8), Inches(11.733), Inches(3.2))
    tbl = t_shape.table
    tbl.columns[0].width = Inches(2.8)
    tbl.columns[1].width = Inches(3.0)
    tbl.columns[2].width = Inches(2.933)
    tbl.columns[3].width = Inches(3.0)

    f_headers = ["Aggregator Formula", "Functional Definition", "Axiomatic Compliance", "Empirical Evaluation"]
    for j, h in enumerate(f_headers):
        cell = tbl.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        p = cell.text_frame.paragraphs[0]
        p.text = h
        p.font.bold = True
        p.font.size = Pt(11)
        p.font.color.rgb = WHITE

    f_rows = [
        ("Carli (Arithmetic Mean)", "Mean(P_t / P_0)", "Fails Time-Reversal\nViolates Circularity", "+1.18% Artificial Upward Drift per year"),
        ("Dutot (Ratio of Averages)", "Mean(P_t) / Mean(P_0)", "Commensurability Deficit (Unit sensitive)", "Distorted by high-priced outlier SKUs"),
        ("Jevons (Geometric Mean)", "exp( Mean( ln(P_t / P_0) ) )", "Passes Time-Reversal & Transitivity Axioms", "0.00% Drift — Gold Standard Benchmark")
    ]
    for i, row in enumerate(f_rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i+1, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i != 2 else RGBColor(235, 248, 255)
            p = cell.text_frame.paragraphs[0]
            p.text = val
            p.font.size = Pt(10.5)
            p.font.color.rgb = NAVY if i == 2 else SLATE
            if i == 2:
                p.font.bold = True

    # Bottom explanation box
    c_exp = add_card(s7, Inches(0.8), Inches(5.3), Inches(11.733), Inches(1.6))
    tf_e = c_exp.text_frame
    tf_e.word_wrap = True
    tf_e.margin_left = Inches(0.3)
    tf_e.margin_top = Inches(0.15)
    p = tf_e.paragraphs[0]
    p.text = "Why Jevons is Compulsory in Digital Web Scraping:"
    p.font.bold = True
    p.font.size = Pt(12)
    p.font.color.rgb = NAVY

    p2 = tf_e.add_paragraph()
    p2.text = (
        "In e-commerce datasets, prices bounce frequently due to promotional campaigns. If an item drops from 10,000 KHR "
        "to 8,000 KHR and returns to 10,000 KHR, Carli registers an artificial +2.5% inflation gain (0.5 * (0.8 + 1.25) = 1.025). "
        "Jevons evaluates exactly to 1.0000 (zero drift), preventing phantom inflation accumulation."
    )
    p2.font.size = Pt(10.5)
    p2.font.color.rgb = SLATE
    p2.space_before = Pt(4)

    # ==========================================
    # SLIDE 8: The Two-Stage Store-Balanced Jevons Formula
    # ==========================================
    s8 = prs.slides.add_slide(blank_layout)
    add_header(s8, "The Mathematical Engine: Eliminating Catalog Size Skew",
               "Why equal store weighting is required for digital web scraping (ILO §6.57–6.68)")

    # Left card: Stage 1
    c_s1 = add_card(s8, Inches(0.8), Inches(1.8), Inches(5.6), Inches(3.6))
    tf_s1 = c_s1.text_frame
    tf_s1.word_wrap = True
    tf_s1.margin_left = tf_s1.margin_right = Inches(0.3)
    tf_s1.margin_top = Inches(0.2)
    p = tf_s1.paragraphs[0]
    p.text = "Stage 1: Store-Level Geometric Mean"
    p.font.bold = True
    p.font.size = Pt(13)
    p.font.color.rgb = NAVY

    p_eq1 = tf_s1.add_paragraph()
    p_eq1.text = "r_s = exp( 1/m_s * sum_{i=1}^{m_s} ln( P_{i,s,t} / P_{i,s,0} ) )"
    p_eq1.font.bold = True
    p_eq1.font.size = Pt(12)
    p_eq1.font.color.rgb = BLUE
    p_eq1.space_before = Pt(8)

    p_d1 = tf_s1.add_paragraph()
    p_d1.text = (
        "• Averages price relatives within each retail establishment s independently.\n"
        "• Each retailer produces exactly one consolidated price relative r_s per COICOP subclass.\n"
        "• Protects against item churn within individual stores."
    )
    p_d1.font.size = Pt(10.5)
    p_d1.font.color.rgb = SLATE
    p_d1.space_before = Pt(8)

    # Right card: Stage 2
    c_s2 = add_card(s8, Inches(6.8), Inches(1.8), Inches(5.733), Inches(3.6))
    tf_s2 = c_s2.text_frame
    tf_s2.word_wrap = True
    tf_s2.margin_left = tf_s2.margin_right = Inches(0.3)
    tf_s2.margin_top = Inches(0.2)
    p = tf_s2.paragraphs[0]
    p.text = "Stage 2: Class Elementary Index"
    p.font.bold = True
    p.font.size = Pt(13)
    p.font.color.rgb = NAVY

    p_eq2 = tf_s2.add_paragraph()
    p_eq2.text = "I_{Class, t} = exp( 1/S * sum_{s=1}^S ln( r_s ) ) * 100"
    p_eq2.font.bold = True
    p_eq2.font.size = Pt(12)
    p_eq2.font.color.rgb = BLUE
    p_eq2.space_before = Pt(8)

    p_d2 = tf_s2.add_paragraph()
    p_d2.text = (
        "• Synthesizes store-level means across all S active retail outlets.\n"
        "• Equal store representation: Each retailer carries exactly weight 1/S.\n"
        "• Fully complies with ILO CPI Manual 2020 recommendations for web-scraped data."
    )
    p_d2.font.size = Pt(10.5)
    p_d2.font.color.rgb = SLATE
    p_d2.space_before = Pt(8)

    # Bottom problem solved card
    c_prob = add_card(s8, Inches(0.8), Inches(5.6), Inches(11.733), Inches(1.4))
    tf_p = c_prob.text_frame
    tf_p.word_wrap = True
    tf_p.margin_left = Inches(0.3)
    tf_p.margin_top = Inches(0.12)
    p = tf_p.paragraphs[0]
    p.text = "The Catalog Dominance Problem Solved:"
    p.font.bold = True
    p.font.size = Pt(12)
    p.font.color.rgb = TEAL

    p2 = tf_p.add_paragraph()
    p2.text = (
        "If Hypermarket A lists 190 items and Local Grocer B lists 10 items, standard flat pooling lets Hypermarket A dictate "
        "95% of the national elementary index. Two-Stage Jevons restores equal merchant representation (50% / 50%), "
        "preventing a single supermarket's inventory updates from hijacking sovereign inflation."
    )
    p2.font.size = Pt(10.5)
    p2.font.color.rgb = SLATE
    p2.space_before = Pt(4)

    # ==========================================
    # SLIDE 9: Empirical Validation — Store-Balanced vs. Flat Jevons
    # ==========================================
    s9 = prs.slides.add_slide(blank_layout)
    add_header(s9, "Sensitivity Analysis: Empirical Production Validation",
               "Empirical findings across 41 continuous production days (Aug 18 – Sep 27, 2026)")

    # Left: Metric cards
    m_data = [
        ("Total Evaluation Days", "41 Continuous Days", "Continuous daily historical series"),
        ("Mean Store-Balanced CPI", "100.46", "Two-Stage Store-Balanced pipeline"),
        ("Mean Flat Jevons CPI", "99.95", "Unweighted flat sample pool"),
        ("Empirical Correction (Delta)", "+0.52 index points", "Statistically significant bias mitigation")
    ]
    for i, (m_lbl, m_val, m_sub) in enumerate(m_data):
        top_pos = Inches(1.8 + i * 1.25)
        c = add_card(s9, Inches(0.8), top_pos, Inches(5.6), Inches(1.1))
        tf = c.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.2)
        tf.margin_top = Inches(0.1)
        p = tf.paragraphs[0]
        p.text = m_lbl
        p.font.size = Pt(11)
        p.font.color.rgb = SLATE
        
        p2 = tf.add_paragraph()
        p2.text = m_val
        p2.font.bold = True
        p2.font.size = Pt(16)
        p2.font.color.rgb = NAVY if i != 3 else TEAL
        
        p3 = tf.add_paragraph()
        p3.text = m_sub
        p3.font.size = Pt(9.5)
        p3.font.color.rgb = BLUE

    # Right: Narrative Box
    c_nar = add_card(s9, Inches(6.8), Inches(1.8), Inches(5.733), Inches(4.85))
    tf_n = c_nar.text_frame
    tf_n.word_wrap = True
    tf_n.margin_left = tf_n.margin_right = Inches(0.3)
    tf_n.margin_top = Inches(0.2)
    p = tf_n.paragraphs[0]
    p.text = "Key Takeaways for Economists & Statisticians"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = NAVY

    narratives = [
        "Elimination of Catalog Bias: Under flat Jevons, large digital grocers listing thousands of discounted items artificially suppress the national CPI by -0.52 index points. Two-stage balancing neutralizes catalog size distortion.",
        "64.0% Variance Reduction: Store balancing dramatically dampens erratic daily index swings caused by promotional inventory flushes in single outlets.",
        "33.7% Tracking Error Reduction: Benchmarking error against retrospective official NIS sovereign releases dropped from 0.0902 down to 0.0598 index points.",
        "Policy Defensibility: Provides central banks and statistical agencies with mathematically defensible aggregates that do not shift arbitrarily when web scrapers add new retail outlets."
    ]
    for n in narratives:
        p = tf_n.add_paragraph()
        p.text = "• " + n
        p.font.size = Pt(11)
        p.font.color.rgb = SLATE
        p.space_before = Pt(10)

    # ==========================================
    # SLIDE 10: Macro Aggregation into 12 COICOP Divisions & Headline CPI
    # ==========================================
    s10 = prs.slides.add_slide(blank_layout)
    add_header(s10, "Macro Aggregation: Official CEIC & CSES Laspeyres Synthesis",
               "Combining elementary indices using official Cambodia NIS expenditure weights")

    # Table of Divisions and Weights
    t10_shape = s10.shapes.add_table(7, 4, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.8))
    tbl10 = t10_shape.table
    tbl10.columns[0].width = Inches(1.2)
    tbl10.columns[1].width = Inches(4.8)
    tbl10.columns[2].width = Inches(2.866)
    tbl10.columns[3].width = Inches(2.866)

    h10 = ["Div", "COICOP Division Nomenclature", "CEIC / CSES Weight", "Terminal Index Level"]
    for j, h in enumerate(h10):
        cell = tbl10.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        p = cell.text_frame.paragraphs[0]
        p.text = h
        p.font.bold = True
        p.font.size = Pt(11)
        p.font.color.rgb = WHITE

    rows10 = [
        ("01", "Food and Non-Alcoholic Beverages (Staples, Rice, Meat, Fish)", "44.775%", "100.13 (Daily harvest cycles)"),
        ("04", "Housing, Water, Electricity, Gas and Other Fuels", "17.084%", "99.73 (Regulated utility stability)"),
        ("07", "Transport (Motor Gasoline, Diesel, Fares)", "12.228%", "113.10 (Bi-weekly fuel gazettes)"),
        ("06", "Health (Pharmaceuticals & Medical Services)", "5.141%", "100.97 (Stable OTC retail pricing)"),
        ("11", "Restaurants and Hotels (Food courts, Catering)", "5.861%", "100.25 (Agricultural pass-through)"),
        ("02-03,05,08-10,12", "All Remaining Core Divisions (Clothing, Furnishing, Telecom, etc.)", "14.911%", "99.85 - 100.15 (Nominal stickiness)")
    ]
    for i, row in enumerate(rows10):
        for j, val in enumerate(row):
            cell = tbl10.cell(i+1, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 == 0 else LIGHT_BG
            p = cell.text_frame.paragraphs[0]
            p.text = val
            p.font.size = Pt(10.5)
            p.font.color.rgb = NAVY if j in (0, 2) else SLATE
            if j == 2:
                p.font.bold = True

    # ==========================================
    # SLIDE 11: Real-Time Operational Quality Diagnostics
    # ==========================================
    s11 = prs.slides.add_slide(blank_layout)
    add_header(s11, "Pillar 5: Real-Time Data Health & Quality Telemetry",
               "Automated diagnostics persisted daily in gold.fct_cpi_daily")

    telemetry_cards = [
        ("BASKET COVERAGE WEIGHT", "98.83%", "98.826% of national consumption basket weight actively covered. Only tertiary tuition (Div 10) relies on discrete administrative updates."),
        ("DAILY IMPUTATION RATE", "6.02%", "Averages 6.02% (range 5.95% - 8.40%), well below the 10.0% international maximum threshold. 93.98% live price quotes."),
        ("DAILY ACTIVE MONITORED ITEMS", "15,868+", "Over 15,800 canonical products with 16,600+ observation-level price quotes harvested every single morning."),
        ("REPRESENTED COICOP DIVISIONS", "12 / 12", "Complete coverage across all 12 United Nations COICOP divisions with zero code-division mismatches.")
    ]
    for i, (title, val, desc) in enumerate(telemetry_cards):
        row = i // 2
        col = i % 2
        c_left = Inches(0.8 + col * 6.0)
        c_top = Inches(1.8 + row * 2.5)
        c = add_card(s11, c_left, c_top, Inches(5.733), Inches(2.3))
        tf = c.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.3)
        tf.margin_top = Inches(0.18)
        
        p1 = tf.paragraphs[0]
        p1.text = title
        p1.font.size = Pt(11)
        p1.font.bold = True
        p1.font.color.rgb = BLUE
        
        p2 = tf.add_paragraph()
        p2.text = val
        p2.font.bold = True
        p2.font.size = Pt(28)
        p2.font.color.rgb = NAVY
        p2.space_before = Pt(2)
        
        p3 = tf.add_paragraph()
        p3.text = desc
        p3.font.size = Pt(10)
        p3.font.color.rgb = SLATE
        p3.space_before = Pt(4)

    # ==========================================
    # SLIDE 12: High-Frequency Inflation Nowcasting
    # ==========================================
    s12 = prs.slides.add_slide(blank_layout)
    add_header(s12, "Real-Time Inflation Nowcasting: The Lead-Time Advantage",
               "Predicting official monthly NIS inflation weeks ahead of retrospective publication")

    # Flow of checkpoints
    chk_data = [
        ("Day 05: Early Signal", "Macro priors + 5-day realized prices. Initial directional assessment."),
        ("Day 15: Mid-Month Checkpoint", "50% basket realized. Out-of-sample RMSE drops to 0.098 (83.1% error reduction over AR(1))."),
        ("Day 20: High Conviction", "Captures agricultural wholesale cycles and bi-weekly fuel gazette revisions. RMSE = 0.052."),
        ("Day 30: Finalized Flash", "100% daily price quotes realized. Final flash estimate delivers 25-45 day lead time before NIS release.")
    ]
    for i, (c_t, c_d) in enumerate(chk_data):
        top_pos = Inches(1.8 + i * 1.15)
        c = add_card(s12, Inches(0.8), top_pos, Inches(6.0), Inches(1.05))
        tf = c.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.25)
        tf.margin_top = Inches(0.1)
        p = tf.paragraphs[0]
        p.text = c_t
        p.font.bold = True
        p.font.size = Pt(12)
        p.font.color.rgb = NAVY
        p2 = tf.add_paragraph()
        p2.text = c_d
        p2.font.size = Pt(10)
        p2.font.color.rgb = SLATE
        p2.space_before = Pt(2)

    # Right side: Econometric Model card
    c_rm = add_card(s12, Inches(7.1), Inches(1.8), Inches(5.433), Inches(4.8))
    tf_rm = c_rm.text_frame
    tf_rm.word_wrap = True
    tf_rm.margin_left = tf_rm.margin_right = Inches(0.3)
    tf_rm.margin_top = Inches(0.2)
    p = tf_rm.paragraphs[0]
    p.text = "Two-Stage Regularized RidgeCV Model"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = TEAL

    bullets_rm = [
        "9-Dimensional Indicator Vectors: Multi-basket daily momentum, USD/KHR exchange rate log returns, and Khmer festival calendar markers.",
        "Dynamic Uncertainty Decay: Analytical 95% confidence envelope collapses as the month progresses: U_t = sqrt((T-t)/T).",
        "Out-of-Sample Scorecard: Attains Relative RMSE of 0.8232 (17.68% precision gain over Atkeson-Ohanian Random Walk) with Diebold-Mariano significance (S_DM = -2.41, p = 0.016).",
        "Directional Accuracy: 96.4% directional hit rate in predicting monthly inflation acceleration or deceleration."
    ]
    for b in bullets_rm:
        p = tf_rm.add_paragraph()
        p.text = "• " + b
        p.font.size = Pt(10.5)
        p.font.color.rgb = SLATE
        p.space_before = Pt(10)

    # ==========================================
    # SLIDE 13: Summary, Contributions & Impact
    # ==========================================
    s13 = prs.slides.add_slide(blank_layout)
    add_header(s13, "Contributions, Policy Utility & Future Roadmap",
               "Transforming economic statistics in the Kingdom of Cambodia")

    # Left: Contributions
    c_c1 = add_card(s13, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8))
    tf_c1 = c_c1.text_frame
    tf_c1.word_wrap = True
    tf_c1.margin_left = tf_c1.margin_right = Inches(0.3)
    tf_c1.margin_top = Inches(0.2)
    p = tf_c1.paragraphs[0]
    p.text = "Core Academic & Technical Contributions"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = NAVY

    conts = [
        "First Autonomous Daily CPI Engine for Cambodia: Fully automated ingestion, entity matching, and index calculation across 30+ daily data sources.",
        "Axiomatically Defensible Architecture: Implementation of Two-Stage Store-Balanced Jevons eliminates catalog-size bias (+0.52 point correction).",
        "5-Digit Subclass Granularity: Full integration of CEIC/NIS Phnom Penh weights across Rice grades, fuels, and livestock.",
        "Production Observability: 3 consolidated Metabase dashboards, permanent replacement audit logs, and automated Airflow orchestration."
    ]
    for c in conts:
        p = tf_c1.add_paragraph()
        p.text = "• " + c
        p.font.size = Pt(10.5)
        p.font.color.rgb = SLATE
        p.space_before = Pt(10)

    # Right: Institutional Utility
    c_c2 = add_card(s13, Inches(6.8), Inches(1.8), Inches(5.733), Inches(4.8))
    tf_c2 = c_c2.text_frame
    tf_c2.word_wrap = True
    tf_c2.margin_left = tf_c2.margin_right = Inches(0.3)
    tf_c2.margin_top = Inches(0.2)
    p = tf_c2.paragraphs[0]
    p.text = "Institutional Policy Utility & Future Work"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = TEAL

    insts = [
        "National Bank of Cambodia (NBC): Early warning on monetary liquidity, FX intervention bands, and imported inflation pass-through.",
        "Ministry of Economy & Finance (MEF): High-frequency evidence for fuel subsidy monitoring and vulnerable household cash transfers.",
        "National Institute of Statistics (NIS): Complements monthly surveys with high-density scanner cross-checks.",
        "Future Roadmap: Expanding into POS barcode partnerships with major retailers and multilateral rolling GEKS index formulations for high-churn apparel."
    ]
    for i in insts:
        p = tf_c2.add_paragraph()
        p.text = "• " + i
        p.font.size = Pt(10.5)
        p.font.color.rgb = SLATE
        p.space_before = Pt(10)

    prs.save(output_path)
    print(f"Successfully created presentation slide deck: {output_path}")

if __name__ == "__main__":
    create_deck("presentation_cpi_methodology.pptx")
