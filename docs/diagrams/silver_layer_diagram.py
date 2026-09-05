"""
Silver Layer Architecture Diagram — Up to Date High-Res Visualization
Features a clean pure white background (#FFFFFF) with crisp, high-contrast, modern styling.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Ellipse

# Canvas Setup with Pure White Background (Optimized dimensions for clean rendering)
fig, ax = plt.subplots(1, 1, figsize=(22, 29))
ax.set_xlim(0, 22)
ax.set_ylim(0, 29)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#FFFFFF')

# ── Color Palette (Crisp, High-Contrast with Pure White Background) ──
C_WHITE = '#FFFFFF'
C_DARK = '#0F172A'
C_MUTED = '#475569'
C_BORDER = '#CBD5E1'

# Stage Accent Colors
C_STAGE_MATCH_BORDER = '#0284C7'    # Sky Blue
C_STAGE_MATCH_BG = '#F0F9FF'
C_STAGE_HYGIENE_BORDER = '#2563EB'  # Royal Blue
C_STAGE_HYGIENE_BG = '#EFF6FF'
C_STAGE_COICOP_BORDER = '#D97706'   # Amber
C_STAGE_COICOP_BG = '#FFFBEB'
C_STAGE_ASSEMBLY_BORDER = '#16A34A' # Emerald Green
C_STAGE_ASSEMBLY_BG = '#F0FDF4'
C_STAGE_HEDONIC_BORDER = '#9333EA'  # Purple
C_STAGE_HEDONIC_BG = '#FAF5FF'
C_STAGE_OPS_BORDER = '#EA580C'      # Orange
C_STAGE_OPS_BG = '#FFF7ED'
C_DAG_BORDER = '#475569'            # Slate
C_DAG_BG = '#F8FAFC'

C_ARROW = '#334155'


def draw_card(ax, x, y, w, h, text='', color=C_WHITE, border='#CBD5E1', fontsize=8.5,
              fontweight='normal', linewidth=1.4, text_color=C_DARK, ha='center', va='center', zorder=2):
    """Draws a rounded card box."""
    box = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.03', facecolor=color,
                         edgecolor=border, linewidth=linewidth, zorder=zorder)
    ax.add_patch(box)
    if text:
        ax.text(x + w/2, y + h/2, text, fontsize=fontsize, fontweight=fontweight,
                ha=ha, va=va, color=text_color, zorder=zorder+1, multialignment='center')


def draw_db_cyl(ax, x, y, w, h, title='', subtitle='', color=C_WHITE, border='#334155', title_color=C_DARK, zorder=3):
    """Draws a database cylinder container."""
    rect = FancyBboxPatch((x, y), w, h - 0.2, boxstyle='round,pad=0.02',
                          facecolor=color, edgecolor=border, linewidth=1.5, zorder=zorder)
    ax.add_patch(rect)
    ell_top = Ellipse((x + w/2, y + h - 0.1), w, 0.25, facecolor=color,
                      edgecolor=border, linewidth=1.5, zorder=zorder+1)
    ax.add_patch(ell_top)
    ell_bot = Ellipse((x + w/2, y + 0.1), w, 0.25, facecolor=color,
                      edgecolor=border, linewidth=1.5, zorder=zorder)
    ax.add_patch(ell_bot)
    
    if subtitle:
        ax.text(x + w/2, y + (h/2) + 0.15, title, fontsize=8.2, fontweight='bold',
                ha='center', va='center', color=title_color, zorder=zorder+2)
        ax.text(x + w/2, y + (h/2) - 0.22, subtitle, fontsize=6.8, fontweight='normal',
                ha='center', va='center', color=C_MUTED, zorder=zorder+2)
    else:
        ax.text(x + w/2, y + h/2, title, fontsize=8.2, fontweight='bold',
                ha='center', va='center', color=title_color, zorder=zorder+2)


def draw_arrow(ax, x1, y1, x2, y2, color=C_ARROW, lw=1.4, style='->', zorder=4):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                               connectionstyle='arc3,rad=0', mutation_scale=11), zorder=zorder)


# ═══════════════════════════════════════════════════════════════════════
# TITLE & HEADER (Pure White Theme)
# ═══════════════════════════════════════════════════════════════════════
ax.text(11, 28.4, 'CAMBODIA DAILY CPI PIPELINE', fontsize=10.5, fontweight='bold',
        ha='center', va='center', color='#0F766E', zorder=5)
ax.text(11, 27.9, 'Silver Layer Architecture & Conformed Store-Level Processing',
        fontsize=18, fontweight='bold', ha='center', va='center', color='#0F172A', zorder=5)
ax.text(11, 27.5, 'Medallion Data Hygiene • 768-dim Vector Item Matching • 4-Tier COICOP Ladder • Hedonic Quality Adjustments',
        fontsize=8.5, ha='center', va='center', color='#64748B', zorder=5)

ax.plot([0.8, 21.2], [27.2, 27.2], color='#E2E8F0', linewidth=1.5, zorder=1)


# ═══════════════════════════════════════════════════════════════════════
# AIRFLOW DAG ORCHESTRATION (Sidebar Left)
# ═══════════════════════════════════════════════════════════════════════
draw_card(ax, 0.6, 8.8, 3.8, 18.0, '', color=C_DAG_BG, border=C_DAG_BORDER, linewidth=1.4, zorder=1)
ax.text(2.5, 26.3, 'AIRFLOW DAG', fontsize=10, fontweight='bold', ha='center', va='center', color='#0F172A', zorder=5)
ax.text(2.5, 26.0, 'silver_dag.py', fontsize=7.2, ha='center', va='center', color='#64748B', zorder=5)
ax.plot([0.9, 4.1], [25.7, 25.7], color='#CBD5E1', linewidth=1, zorder=2)

dag_tasks = [
    ('1. silver_item_matching', 'Vector + RapidFuzz\n+ Spec Guards (Daily)', C_WHITE, '#0284C7'),
    ('2. item_auto_review', 'Gemini AI + Rule Arb\n(silver.needs_review)', C_WHITE, '#0284C7'),
    ('3. dbt_seed', 'Load Overrides & Weights\n(dbt seeds)', C_WHITE, '#2563EB'),
    ('4. gemini_coicop', 'Hybrid AI COICOP\n(3-Key Round-Robin)', C_WHITE, '#D97706'),
    ('5. hedonic_regression', 'Div 08/09 OLS Tech Spec\nAdjustment Engine', C_WHITE, '#9333EA'),
    ('6. dbt_silver_run', 'int_prices_cleaned &\nclean_store_prices', C_WHITE, '#16A34A'),
    ('7. dbt_silver_test', 'Schema & Custom Business\nLogic Assertions', C_WHITE, '#16A34A'),
]

for idx, (tname, tdesc, tcol, tborder) in enumerate(dag_tasks):
    y_box = 23.3 - (idx * 2.05)
    draw_card(ax, 0.9, y_box, 3.2, 1.6, '', color=tcol, border=tborder, linewidth=1.3, zorder=2)
    ax.text(2.5, y_box + 1.15, tname, fontsize=7.0, fontweight='bold', ha='center', va='center', color=tborder, zorder=5)
    ax.text(2.5, y_box + 0.55, tdesc, fontsize=6.2, ha='center', va='center', color='#475569', zorder=5)
    
    if idx < len(dag_tasks) - 1:
        draw_arrow(ax, 2.5, y_box, 2.5, y_box - 0.45, color='#64748B', lw=1.2)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 0: VECTOR ITEM MATCHING & DEDUPLICATION (Top Main Stage)
# ═══════════════════════════════════════════════════════════════════════
draw_card(ax, 4.8, 22.4, 16.6, 4.6, '', color=C_STAGE_MATCH_BG, border=C_STAGE_MATCH_BORDER, linewidth=1.5, zorder=1)
ax.text(5.1, 26.6, 'STAGE 0: INCREMENTAL ITEM MATCHING & CANONICAL IDENTITY RESOLUTION', 
        fontsize=9.8, fontweight='bold', ha='left', va='center', color='#0369A1', zorder=5)
ax.text(5.1, 26.25, 'pipeline/item_matcher.py  •  pipeline/vector_item_matcher.py  •  pipeline/gemini_item_reviewer.py', 
        fontsize=7.2, ha='left', va='center', color='#64748B', zorder=5)

# Ingestion source
draw_db_cyl(ax, 5.1, 22.8, 3.2, 3.1, 'bronze.raw_prices', 'Daily Raw Scrapes\n(raw_price_id, store_id,\nitem_desc, price)', 
            C_WHITE, '#0284C7', title_color='#0369A1')

# Fast-path History Cache Check
draw_card(ax, 8.7, 23.9, 3.3, 1.6, 'Fast Cache Check:\n(store_slug, raw_sku)\nin item_match_log', 
          color=C_WHITE, border='#0284C7', fontsize=6.8, fontweight='bold')

# Ladder Box
draw_card(ax, 12.3, 22.7, 4.8, 3.2, '', color=C_WHITE, border='#0284C7', linewidth=1.3)
ax.text(14.7, 25.5, '5-STEP MATCHING LADDER', fontsize=7.5, fontweight='bold', ha='center', va='center', color='#0369A1', zorder=5)

matching_ladder = [
    ('1. Barcode Exact Match', 'conf = 1.000', '#16A34A'),
    ('2. SKU / Native ID Match', 'conf = 1.000', '#16A34A'),
    ('3. Normalized Text Match', 'conf = 1.000', '#16A34A'),
    ('4. RapidFuzz + Spec Guards', 'RAM, Pack check', '#0284C7'),
    ('5. 768-dim Vector Cosine', 'all-mpnet-base-v2', '#0284C7'),
]
for mi, (mtitle, msub, mcol) in enumerate(matching_ladder):
    y_m = 24.9 - mi * 0.48
    ax.text(12.6, y_m, f'• {mtitle}', fontsize=6.2, fontweight='bold', ha='left', va='center', color=mcol, zorder=5)
    ax.text(16.8, y_m, msub, fontsize=5.8, ha='right', va='center', color='#64748B', zorder=5)

# Decision Routing
draw_card(ax, 17.4, 24.8, 3.6, 1.1, 'Score ≥ 0.88: APPROVE_MATCH\n(Map to existing UUID)', 
          color='#ECFDF5', border='#16A34A', fontsize=6.2, fontweight='bold', text_color='#15803D')
draw_card(ax, 17.4, 23.6, 3.6, 1.1, '0.75 ≤ Score < 0.88: needs_review\n(Gemini Pro/Flash Arbitrator)', 
          color='#FFFBEB', border='#D97706', fontsize=6.2, fontweight='bold', text_color='#B45309')
draw_card(ax, 17.4, 22.4, 3.6, 1.1, 'Score < 0.75: SPLIT_NEW\n(silver.canonical_items)', 
          color='#FEF2F2', border='#DC2626', fontsize=6.2, fontweight='bold', text_color='#B91C1C')

draw_arrow(ax, 8.3, 24.6, 8.7, 24.6, color='#0284C7', lw=1.3)
draw_arrow(ax, 12.0, 24.6, 12.3, 24.6, color='#0284C7', lw=1.3)
draw_arrow(ax, 17.1, 25.3, 17.4, 25.3, color='#16A34A', lw=1.1)
draw_arrow(ax, 17.1, 24.1, 17.4, 24.1, color='#D97706', lw=1.1)
draw_arrow(ax, 17.1, 22.9, 17.4, 22.9, color='#DC2626', lw=1.1)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 1: INGESTION HYGIENE (Intermediate Cleaning)
# ═══════════════════════════════════════════════════════════════════════
draw_card(ax, 4.8, 17.2, 16.6, 4.8, '', color=C_STAGE_HYGIENE_BG, border=C_STAGE_HYGIENE_BORDER, linewidth=1.5, zorder=1)
ax.text(5.1, 21.6, 'STAGE 1: INGESTION HYGIENE & FEATURE NORMALIZATION', 
        fontsize=9.8, fontweight='bold', ha='left', va='center', color='#1D4ED8', zorder=5)
ax.text(5.1, 21.25, 'dbt/models/silver/intermediate/int_prices_cleaned.sql  •  macros/clean_product_name.sql', 
        fontsize=7.2, ha='left', va='center', color='#64748B', zorder=5)

# Input tables
draw_db_cyl(ax, 5.1, 17.7, 3.0, 3.1, 'bronze.raw_prices', 'Joined with\nsilver.item_match_log\n(raw_price_id → item_id)', 
            C_WHITE, '#2563EB', title_color='#1D4ED8')
draw_db_cyl(ax, 8.4, 17.7, 3.0, 3.1, 'staging.exchange_rates', 'MEF Daily Rates\n(USD → KHR FX\nfallback: 4,044 KHR)', 
            C_WHITE, '#2563EB', title_color='#1D4ED8')

# Transformation Cards
draw_card(ax, 11.8, 17.5, 9.2, 3.4, '', color=C_WHITE, border='#2563EB', linewidth=1.3)
ax.text(16.4, 20.5, 'DETERMINISTIC DATA HYGIENE RULES', fontsize=7.5, fontweight='bold', ha='center', va='center', color='#1D4ED8', zorder=5)

hygiene_rules = [
    ('MEF FX Conversion', 'Converts USD to KHR; original_price_khr computed once', '#2563EB'),
    ('Khmer Text Norm', 'Translates Khmer digits (0-9), unescapes HTML, strips promo', '#2563EB'),
    ('Unit Parsing', 'Extracts qty & units (g, kg, ml, L, pack) across 40+ synonyms', '#16A34A'),
    ('Unit Price Derived', 'Computes unit_price_khr = price_khr / size_value', '#16A34A'),
    ('Promo Clamping', 'Clamps promo discount into [0%, 95%], tags on_promo', '#D97706'),
    ('Outlier & Eligibility', 'Flags extreme prices (> 100M KHR) and tags cpi_eligible', '#DC2626'),
]
for hi, (htitle, hdesc, hcol) in enumerate(hygiene_rules):
    y_h = 20.0 - hi * 0.44
    ax.text(12.1, y_h, f'• {htitle}:', fontsize=6.2, fontweight='bold', ha='left', va='center', color=hcol, zorder=5)
    ax.text(15.2, y_h, hdesc, fontsize=6.0, ha='left', va='center', color='#334155', zorder=5)

draw_arrow(ax, 6.6, 22.8, 6.6, 20.8, color='#2563EB', lw=1.3)
draw_arrow(ax, 11.4, 19.2, 11.8, 19.2, color='#2563EB', lw=1.3)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 2: 4-TIER COICOP CLASSIFICATION LADDER
# ═══════════════════════════════════════════════════════════════════════
draw_card(ax, 4.8, 11.6, 16.6, 5.2, '', color=C_STAGE_COICOP_BG, border=C_STAGE_COICOP_BORDER, linewidth=1.5, zorder=1)
ax.text(5.1, 16.4, 'STAGE 2: 4-TIER HYBRID COICOP CLASSIFICATION LADDER', 
        fontsize=9.8, fontweight='bold', ha='left', va='center', color='#B45309', zorder=5)
ax.text(5.1, 16.05, 'int_coicop_classified.sql  •  macros/coicop_classify_macro.sql  •  hybrid_embeddings_classifier.py', 
        fontsize=7.2, ha='left', va='center', color='#64748B', zorder=5)

draw_db_cyl(ax, 5.1, 12.1, 3.2, 3.4, 'Operational Seeds\n& Overrides', '• coicop_override.csv\n• coicop_override_manual\n• coicop_category_map\n• coicop_store_defaults', 
            C_WHITE, '#D97706', title_color='#B45309')

draw_card(ax, 8.7, 12.0, 12.3, 3.8, '', color=C_WHITE, border='#D97706', linewidth=1.3)
ax.text(14.85, 15.4, 'HIERARCHICAL COICOP CLASSIFICATION RESOLUTION', fontsize=7.5, fontweight='bold', ha='center', va='center', color='#B45309', zorder=5)

coicop_tiers = [
    ('TIER 1: Authority Overrides', 'Exact match on barcode, product key, or store pattern', 'conf = 1.000', '#16A34A'),
    ('TIER 2: 15 Pure Store Locks', 'Gasoline → 07, Telecom → 08, Housing → 04, Hotels → 11', 'conf = 0.850', '#0284C7'),
    ('TIER 3: 768-dim Vector Embed', 'Cosine vs 12 UN COICOP spaces (Panadol 06 vs Cetaphil 12)', 'conf = 0.80–0.95', '#2563EB'),
    ('TIER 4: Gemini Pro/Flash AI', '3-Key thread-safe pool, auto-failover, dim_coicop_ai_cache', 'conf = AI Score', '#9333EA'),
    ('TIER 5: Category Map', 'Deterministic mapping from retailer taxonomy', 'conf = 0.900', '#D97706'),
    ('TIER 6: Store Defaults', 'Coarse store-level defaults or marked UNCLASSIFIED', 'conf = 0.800', '#64748B'),
]
for ci, (ctitle, cdesc, cconf, ccol) in enumerate(coicop_tiers):
    y_c = 14.8 - ci * 0.48
    ax.text(9.0, y_c, f'• {ctitle}:', fontsize=6.2, fontweight='bold', ha='left', va='center', color=ccol, zorder=5)
    ax.text(13.2, y_c, cdesc, fontsize=5.8, ha='left', va='center', color='#334155', zorder=5)
    draw_card(ax, 19.1, y_c - 0.16, 1.6, 0.32, cconf, color='#FEF3C7', border='#F59E0B', fontsize=5.5, fontweight='bold', text_color='#92400E')

draw_arrow(ax, 8.3, 13.8, 8.7, 13.8, color='#D97706', lw=1.3)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 3: UNIFIED SILVER FACT ASSEMBLY (clean_store_prices)
# ═══════════════════════════════════════════════════════════════════════
draw_card(ax, 4.8, 5.8, 16.6, 5.4, '', color=C_STAGE_ASSEMBLY_BG, border=C_STAGE_ASSEMBLY_BORDER, linewidth=1.5, zorder=1)
ax.text(5.1, 10.8, 'STAGE 3: FINAL ASSEMBLY — UNIFIED CONFORMED SILVER OBSERVATIONS', 
        fontsize=9.8, fontweight='bold', ha='left', va='center', color='#15803D', zorder=5)
ax.text(5.1, 10.45, 'dbt/models/silver/clean_store_prices.sql  •  Incremental (delete+insert on raw_price_id)', 
        fontsize=7.2, ha='left', va='center', color='#64748B', zorder=5)

draw_db_cyl(ax, 5.1, 6.2, 5.8, 3.8, 'silver.clean_store_prices', 
            'PK: raw_price_id | FK: item_id, store_slug\n'
            '• scrape_date, store_slug, source_name\n'
            '• name_raw, name_clean, brand, barcode\n'
            '• price_khr, original_price_khr, unit_price_khr\n'
            '• size_value, size_unit, pack_qty\n'
            '• discount_pct, on_promo\n'
            '• coicop_division (01-12), coicop_code (XX.X.X)\n'
            '• coicop_method, coicop_confidence\n'
            '• is_outlier, cpi_eligible, scraped_at',
            C_WHITE, '#16A34A', title_color='#15803D')

draw_card(ax, 11.3, 6.2, 9.7, 3.8, '', color=C_WHITE, border='#16A34A', linewidth=1.3)
ax.text(16.15, 9.6, 'SILVER DATA HYGIENE & CLASSIFICATION GATES', fontsize=7.5, fontweight='bold', ha='center', va='center', color='#15803D', zorder=5)

assembly_rules = [
    ('C2 Zero-Price Gate', 'Strict WHERE price_khr > 0 filter (prevents log(0) errors)', '#DC2626'),
    ('Hierarchical Coalesce', 'int_coicop_classified → overrides → purity → AI cache → cat_map', '#15803D'),
    ('5-Digit COICOP Formatter', 'Maps 2-digit divisions to 5-digit international codes (01 → 01.1.1)', '#0284C7'),
    ('Confidence Propagation', 'Preserves audit trail with coicop_confidence (1.000, 0.900, 0.850)', '#2563EB'),
    ('Index Optimization', 'B-Tree Indexes on (scrape_date, store_slug), (store_slug, item_id)', '#475569'),
]
for ai_idx, (atitle, adesc, acol) in enumerate(assembly_rules):
    y_a = 9.1 - ai_idx * 0.54
    ax.text(11.6, y_a, f'• {atitle}:', fontsize=6.2, fontweight='bold', ha='left', va='center', color=acol, zorder=5)
    ax.text(14.6, y_a, adesc, fontsize=5.8, ha='left', va='center', color='#334155', zorder=5)

draw_arrow(ax, 14.5, 17.2, 14.5, 16.8, color='#2563EB', lw=1.3)
draw_arrow(ax, 14.5, 11.6, 14.5, 11.2, color='#16A34A', lw=1.3)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 4 & 5: HEDONIC QUALITY ADJUSTMENT & SYSTEM TABLES (Bottom Row)
# ═══════════════════════════════════════════════════════════════════════
# Hedonic Box (Left)
draw_card(ax, 0.6, 1.2, 9.8, 4.2, '', color=C_STAGE_HEDONIC_BG, border=C_STAGE_HEDONIC_BORDER, linewidth=1.5, zorder=1)
ax.text(0.9, 5.0, 'HEDONIC QUALITY ADJUSTMENT (Div 08/09 Tech Specs)', 
        fontsize=8.2, fontweight='bold', ha='left', va='center', color='#7E22CE', zorder=5)
ax.text(0.9, 4.65, 'pipeline/hedonic_regression.py  •  Semi-log OLS Multi-Attribute Model', 
        fontsize=6.2, ha='left', va='center', color='#64748B', zorder=5)

hedonic_details = [
    '• Target: Division 08 (Telecom hardware) & 09 (Electronics)',
    '• Model: ln(price) ~ RAM + Storage + Screen + Camera + 5G',
    '• Baseline: Trailing 3-month rolling spec baseline',
    '• Result: Isolates true price changes from tech advances',
    '• Output: silver.hedonic_adjusted_prices',
]
for hdi, htext in enumerate(hedonic_details):
    ax.text(0.9, 4.2 - hdi * 0.40, htext, fontsize=6.0, ha='left', va='center', color='#334155', zorder=5)

# Operational & System Tables (Right)
draw_card(ax, 10.8, 1.2, 10.6, 4.2, '', color=C_STAGE_OPS_BG, border=C_STAGE_OPS_BORDER, linewidth=1.5, zorder=1)
ax.text(11.1, 5.0, 'SILVER OPERATIONAL & SYSTEM AUDIT TABLES', 
        fontsize=8.2, fontweight='bold', ha='left', va='center', color='#C2410C', zorder=5)
ax.text(11.1, 4.65, 'PostgreSQL 16 Conformed Audit Trail & Memoization', 
        fontsize=6.2, ha='left', va='center', color='#64748B', zorder=5)

ops_tables_list = [
    ('silver.canonical_items', 'Deterministic UUID canonical item master with specs'),
    ('silver.item_match_log', 'Audit log of raw_price_id → item_id mapping'),
    ('silver.needs_review', 'Triage queue for borderline vector matches (0.75-0.88)'),
    ('silver.dim_coicop_ai_cache', 'Persistent memoized cache for Gemini AI classifications'),
    ('silver.classification_queue', 'Manual & automated triage queue for unclassified products'),
]
for oi, (otbl, odesc) in enumerate(ops_tables_list):
    y_o = 4.2 - oi * 0.40
    ax.text(11.1, y_o, f'• {otbl}:', fontsize=6.0, fontweight='bold', ha='left', va='center', color='#C2410C', zorder=5)
    ax.text(14.5, y_o, odesc, fontsize=5.8, ha='left', va='center', color='#334155', zorder=5)


# ═══════════════════════════════════════════════════════════════════════
# FOOTER / LEGEND (Pure White Theme)
# ═══════════════════════════════════════════════════════════════════════
ax.plot([0.6, 21.4], [0.8, 0.8], color='#E2E8F0', linewidth=1.2, zorder=1)

legend_items = [
    ('#0284C7', '#F0F9FF', 'Stage 0: Item Matching'),
    ('#2563EB', '#EFF6FF', 'Stage 1: Ingestion Hygiene'),
    ('#D97706', '#FFFBEB', 'Stage 2: COICOP Ladder'),
    ('#16A34A', '#F0FDF4', 'Stage 3: Clean Store Facts'),
    ('#9333EA', '#FAF5FF', 'Stage 4: Hedonics'),
    ('#EA580C', '#FFF7ED', 'Operational Tables'),
]

for li, (lborder, lbg, ltext) in enumerate(legend_items):
    lx = 0.8 + li * 3.4
    draw_card(ax, lx, 0.25, 0.6, 0.35, '', color=lbg, border=lborder, linewidth=1.2)
    ax.text(lx + 0.72, 0.42, ltext, fontsize=6.2, fontweight='bold', ha='left', va='center', color='#1E293B', zorder=5)


# ═══════════════════════════════════════════════════════════════════════
# RENDER & SAVE TO DISK
# ═══════════════════════════════════════════════════════════════════════
output_path = r'D:\CPI PIPELINE\docs\diagrams\silver_layer_architecture.png'
plt.savefig(output_path, dpi=140, bbox_inches='tight', facecolor='#FFFFFF', edgecolor='none', pad_inches=0.3)
plt.close()
print(f"[SUCCESS] Clean White Background Diagram successfully rendered to: {output_path}")
