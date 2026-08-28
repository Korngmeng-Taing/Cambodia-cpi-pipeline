"""
Silver Layer Architecture Diagram — Code-Derived Visualization
Generates a comprehensive flowchart of the CPI Silver layer pipeline.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(28, 38))
ax.set_xlim(0, 28)
ax.set_ylim(0, 38)
ax.axis('off')
fig.patch.set_facecolor('#FAFBFC')

# ── Color Palette ──
C_BRONZE = '#E3F2FD'
C_BRONZE_BORDER = '#1E88E5'
C_SILVER = '#E8F5E9'
C_SILVER_BORDER = '#2E7D32'
C_GOLD = '#FFF8E1'
C_GOLD_BORDER = '#F57F17'
C_WHITE = '#FFFFFF'
C_HEADER = '#1B5E20'
C_TEXT = '#212529'
C_LIGHT_GRAY = '#F5F5F5'
C_ARROW = '#546E7A'
C_STAGE_BG = '#F1F8E9'
C_TABLE_BG = '#FFFFFF'
C_HEDONIC = '#F3E5F5'
C_HEDONIC_BORDER = '#8E24AA'
C_OPS = '#FFF3E0'
C_OPS_BORDER = '#E65100'
C_DAG_BG = '#ECEFF1'
C_DAG_BORDER = '#455A64'

def draw_box(ax, x, y, w, h, text, color=C_WHITE, border='#333333', fontsize=9,
             fontweight='normal', alpha=1.0, linewidth=1.5, style='round,pad=0.02',
             text_color=C_TEXT, ha='center', va='center'):
    box = FancyBboxPatch((x, y), w, h, boxstyle=style, facecolor=color,
                         edgecolor=border, linewidth=linewidth, alpha=alpha,
                         zorder=2)
    ax.add_patch(box)
    ax.text(x + w/2, y + h/2, text, fontsize=fontsize, fontweight=fontweight,
            ha=ha, va=va, color=text_color, zorder=3, wrap=True,
            multialignment='center',
            bbox=dict(boxstyle='round,pad=0.01', facecolor='none', edgecolor='none'))

def draw_db(ax, x, y, w, h, text, color=C_WHITE, border='#333333', fontsize=8):
    # Cylinder shape for database
    from matplotlib.patches import Ellipse
    # Body
    rect = FancyBboxPatch((x, y), w, h - 0.15, boxstyle='round,pad=0.02',
                           facecolor=color, edgecolor=border, linewidth=1.5, zorder=2)
    ax.add_patch(rect)
    # Top ellipse
    ell_top = Ellipse((x + w/2, y + h - 0.075), w, 0.25, facecolor=color,
                       edgecolor=border, linewidth=1.5, zorder=3)
    ax.add_patch(ell_top)
    # Bottom ellipse
    ell_bot = Ellipse((x + w/2, y + 0.075), w, 0.25, facecolor=color,
                       edgecolor=border, linewidth=1.5, zorder=2)
    ax.add_patch(ell_bot)
    ax.text(x + w/2, y + h/2, text, fontsize=fontsize, fontweight='bold',
            ha='center', va='center', color=C_TEXT, zorder=4, multialignment='center')

def draw_arrow(ax, x1, y1, x2, y2, color=C_ARROW, lw=1.5, style='->', zorder=1):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                               connectionstyle='arc3,rad=0'), zorder=zorder)

def draw_curved_arrow(ax, x1, y1, x2, y2, color=C_ARROW, lw=1.5, rad=0.2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                               connectionstyle=f'arc3,rad={rad}'), zorder=5)

# ═══════════════════════════════════════════════════════════════════════
# TITLE
# ═══════════════════════════════════════════════════════════════════════
ax.text(14, 37.5, 'SILVER LAYER ARCHITECTURE', fontsize=22, fontweight='bold',
        ha='center', va='center', color=C_HEADER, zorder=5)
ax.text(14, 37.05, 'Cambodia Daily CPI Pipeline — Code-Derived Diagram',
        fontsize=12, ha='center', va='center', color='#616161', zorder=5)
ax.plot([2, 26], [36.8, 36.8], color=C_SILVER_BORDER, linewidth=2, zorder=1)

# ═══════════════════════════════════════════════════════════════════════
# STAGE 0: ITEM MATCHING (Top section)
# ═══════════════════════════════════════════════════════════════════════
# Stage background
stage0_bg = FancyBboxPatch((1, 30.5), 26, 6.2, boxstyle='round,pad=0.1',
                            facecolor='#E8F5E9', edgecolor='#2E7D32',
                            linewidth=2, alpha=0.3, zorder=0)
ax.add_patch(stage0_bg)
ax.text(14, 36.3, 'STAGE 0: ITEM MATCHING', fontsize=14, fontweight='bold',
        ha='center', va='center', color=C_HEADER, zorder=5)
ax.text(14, 36.0, 'pipeline/item_matcher.py + vector_item_matcher.py',
        fontsize=9, ha='center', va='center', color='#616161', zorder=5)

# Bronze input
draw_db(ax, 2, 34.5, 3.5, 1.0, 'bronze.raw_prices\n(raw_price_id, store_id,\nitem_description_raw, price)', C_BRONZE, C_BRONZE_BORDER, 7)

# Load cache
draw_box(ax, 7, 34.8, 3.2, 0.7, 'Load Cache:\nsilver.canonical_items', '#C8E6C9', C_SILVER_BORDER, 8)

# Matching ladder
draw_box(ax, 11.5, 31.0, 14.5, 5.0, '', C_WHITE, C_SILVER_BORDER, linewidth=1)
ax.text(18.75, 35.7, 'MATCHING LADDER (per raw_price_id)', fontsize=10, fontweight='bold',
        ha='center', va='center', color=C_HEADER, zorder=5)

# Match steps
match_steps = [
    ('1. Barcode Exact', 'conf=1.0', '#C8E6C9'),
    ('2. SKU Exact', 'conf=1.0', '#C8E6C9'),
    ('3. Exact Name', 'conf=1.0', '#C8E6C9'),
    ('4. Fuzzy Text + Spec Guard', 'RapidFuzz + is_spec_compatible', '#DCEDC8'),
    ('5. Vector Embedding (768-dim)', 'cosine_sim + Gemini AI Arbitrator', '#DCEDC8'),
]
for i, (label, sub, color) in enumerate(match_steps):
    y_pos = 35.1 - i * 0.75
    draw_box(ax, 12, y_pos, 6.5, 0.6, label, color, C_SILVER_BORDER, 8, fontweight='bold')
    ax.text(18.8, y_pos + 0.3, sub, fontsize=7, ha='center', va='center', color='#616161', zorder=5)

# Decisions
draw_box(ax, 19.5, 34.8, 3.5, 0.6, '>= 0.95: MATCH\nLOG', '#A5D6A7', C_SILVER_BORDER, 7, fontweight='bold')
draw_box(ax, 19.5, 34.0, 3.5, 0.6, '0.85-0.95:\nNEEDS REVIEW', '#FFE082', '#F57F17', 7, fontweight='bold')
draw_box(ax, 19.5, 33.2, 3.5, 0.6, '< 0.85: VECTOR\nMATCH', '#B2DFDB', '#00796B', 7, fontweight='bold')
draw_box(ax, 19.5, 32.4, 3.5, 0.6, '< 0.65: CREATE\nNEW ITEM', '#FFCCBC', '#BF360C', 7, fontweight='bold')

# Confidence thresholds
draw_box(ax, 23.5, 34.8, 2.2, 0.6, '>= 0.80:\nAPPROVE', '#A5D6A7', C_SILVER_BORDER, 7)
draw_box(ax, 23.5, 34.0, 2.2, 0.6, '0.65-0.80:\nGEMINI AI ARB', '#FFE082', '#F57F17', 7)
draw_box(ax, 23.5, 33.2, 2.2, 0.6, '< 0.65:\nSPLIT_NEW', '#FFCCBC', '#BF360C', 7)

# Output tables for Stage 0
draw_db(ax, 2, 31.0, 3.5, 0.9, 'silver.canonical_items\n(item_id UUID PK,\ncanonical_name, barcode)', C_TABLE_BG, C_SILVER_BORDER, 7)
draw_db(ax, 6.5, 31.0, 3.5, 0.9, 'silver.item_match_log\n(raw_price_id → item_id,\nmatch_method, confidence)', C_TABLE_BG, C_SILVER_BORDER, 7)
draw_db(ax, 11, 31.0, 3.5, 0.9, 'silver.needs_review\n(borderline pairs,\nauto-reviewed by Gemini)', C_TABLE_BG, '#F57F17', 7)

# Arrows Stage 0
draw_arrow(ax, 5.5, 35.0, 7, 35.15, C_SILVER_BORDER, 2)
draw_arrow(ax, 10.2, 35.15, 11.5, 35.15, C_SILVER_BORDER, 2)
draw_arrow(ax, 18.5, 35.1, 19.5, 35.1, C_SILVER_BORDER, 1.5)
draw_arrow(ax, 18.5, 34.5, 19.5, 34.3, C_SILVER_BORDER, 1.5)
draw_arrow(ax, 18.5, 33.8, 19.5, 33.5, C_SILVER_BORDER, 1.5)
draw_arrow(ax, 18.5, 33.0, 19.5, 32.7, C_SILVER_BORDER, 1.5)
draw_arrow(ax, 23.0, 35.1, 23.5, 35.1, C_SILVER_BORDER, 1)
draw_arrow(ax, 23.0, 34.3, 23.5, 34.3, C_SILVER_BORDER, 1)
draw_arrow(ax, 23.0, 33.5, 23.5, 33.5, C_SILVER_BORDER, 1)

# ═══════════════════════════════════════════════════════════════════════
# STAGE 1: INGESTION HYGIENE
# ═══════════════════════════════════════════════════════════════════════
stage1_bg = FancyBboxPatch((1, 24.5), 26, 5.8, boxstyle='round,pad=0.1',
                            facecolor='#E3F2FD', edgecolor='#1E88E5',
                            linewidth=2, alpha=0.3, zorder=0)
ax.add_patch(stage1_bg)
ax.text(14, 29.9, 'STAGE 1: INGESTION HYGIENE', fontsize=14, fontweight='bold',
        ha='center', va='center', color='#0D47A1', zorder=5)
ax.text(14, 29.6, 'dbt/models/silver/intermediate/int_prices_cleaned.sql',
        fontsize=9, ha='center', va='center', color='#616161', zorder=5)

# Input tables
draw_db(ax, 2, 28.2, 3.2, 0.9, 'bronze.raw_prices\n+ silver.item_match_log', C_BRONZE, C_BRONZE_BORDER, 7)
draw_db(ax, 6, 28.2, 3.2, 0.9, 'staging.exchange_rates\n(MEF USD/KHR daily rate,\nfallback 4044)', C_BRONZE, C_BRONZE_BORDER, 7)

# Transformations box
draw_box(ax, 10, 25.0, 16.5, 4.2, '', C_WHITE, '#1E88E5', linewidth=1.5)
ax.text(18.25, 28.9, 'TRANSFORMATIONS', fontsize=10, fontweight='bold',
        ha='center', va='center', color='#0D47A1', zorder=5)

transforms = [
    'JOIN raw_prices ↔ item_match_log → item_id',
    'USD → KHR via MEF daily rate (fallback 4044)',
    'Parse size_norm → size_value + size_unit (regex)',
    'Normalize 40+ unit synonyms (g,kg,ml,l,pack,can,bottle...)',
    'unit_price_khr = price_khr / size_value',
    'Promo clamping: discount_pct ∈ [0%, 95%]',
    'Outlier flag: price > 100M KHR',
    'name_clean: HTML→strip prices→Khmer→Arabic→uppercase',
]
for i, t in enumerate(transforms):
    ax.text(10.5, 28.4 - i * 0.4, f'• {t}', fontsize=7.5, ha='left', va='center',
            color=C_TEXT, zorder=5)

# Output table
draw_db(ax, 2, 25.0, 7.5, 1.2, 'staging.int_prices_cleaned\n(raw_price_id, item_id, store_slug, name_clean, price_khr,\nunit_price_khr, discount_pct, on_promo, is_outlier, cpi_eligible)',
        '#BBDEFB', '#1565C0', 7)

# Arrows
draw_arrow(ax, 3.6, 28.2, 3.6, 26.2, '#1E88E5', 2)
draw_arrow(ax, 7.6, 28.2, 6, 26.2, '#1E88E5', 2)
draw_arrow(ax, 10, 27.0, 9.5, 26.0, '#1E88E5', 2)

# ═══════════════════════════════════════════════════════════════════════
# STAGE 2: COICOP CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════
stage2_bg = FancyBboxPatch((1, 17.0), 26, 7.2, boxstyle='round,pad=0.1',
                            facecolor='#FFF8E1', edgecolor='#F57F17',
                            linewidth=2, alpha=0.3, zorder=0)
ax.add_patch(stage2_bg)
ax.text(14, 23.9, 'STAGE 2: COICOP CLASSIFICATION', fontsize=14, fontweight='bold',
        ha='center', va='center', color='#E65100', zorder=5)
ax.text(14, 23.6, 'int_coicop_classified.sql + macros/coicop_classify_macro.sql',
        fontsize=9, ha='center', va='center', color='#616161', zorder=5)

# Input
draw_db(ax, 2, 22.0, 3.5, 0.8, 'int_prices_cleaned\n+ canonical_items', '#BBDEFB', '#1565C0', 7)
draw_db(ax, 6.5, 22.0, 3.5, 0.8, 'Override Tables\n+ AI Cache + Seeds', C_OPS, C_OPS_BORDER, 7)

# 6-tier ladder
draw_box(ax, 11, 17.5, 15.5, 5.5, '', C_WHITE, '#E65100', linewidth=1.5)
ax.text(18.75, 22.7, '6-TIER COICOP RESOLUTION LADDER', fontsize=10, fontweight='bold',
        ha='center', va='center', color='#E65100', zorder=5)

tiers = [
    ('TIER 1: Override Exact', 'barcode, product_key, name+store', 'conf=1.000', '#C8E6C9'),
    ('TIER 2: Store Purity', '15 pure stores: Gas→07, Telecom→08...', 'conf=0.850', '#C8E6C9'),
    ('TIER 3: Override Global', 'name substring rules', 'conf=1.000', '#C8E6C9'),
    ('TIER 4: Gemini AI Cache', 'dim_coicop_ai_cache (pre-warmed)', 'conf=ai_score', '#DCEDC8'),
    ('TIER 5: Category Map', 'coicop_category_map', 'conf=0.900', '#FFF9C4'),
    ('TIER 6: Store Default', 'coicop_store_defaults + UNCLASSIFIED', 'conf=0.800', '#FFE0B2'),
]
for i, (label, sub, conf, color) in enumerate(tiers):
    y_pos = 22.2 - i * 0.75
    draw_box(ax, 11.5, y_pos, 5.5, 0.6, label, color, '#E65100', 8, fontweight='bold')
    ax.text(17.3, y_pos + 0.3, sub, fontsize=7, ha='left', va='center', color='#616161', zorder=5)
    draw_box(ax, 23.5, y_pos, 2.5, 0.6, conf, '#FFF9C4', '#F57F17', 7)

# Output
draw_db(ax, 2, 17.5, 7.5, 1.2, 'staging.int_coicop_classified\n(item_id, store_slug, coicop_division, coicop_code,\ncoicop_method, coicop_confidence)',
        '#FFF9C4', '#F57F17', 7)

# Arrows
draw_arrow(ax, 3.75, 22.0, 3.75, 18.7, '#E65100', 2)
draw_arrow(ax, 8.25, 22.0, 6, 18.7, '#E65100', 2)
draw_arrow(ax, 11, 20.0, 9.5, 18.5, '#E65100', 2)

# ═══════════════════════════════════════════════════════════════════════
# STAGE 3: FINAL ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════
stage3_bg = FancyBboxPatch((1, 10.0), 26, 6.7, boxstyle='round,pad=0.1',
                            facecolor='#E8F5E9', edgecolor='#2E7D32',
                            linewidth=2, alpha=0.3, zorder=0)
ax.add_patch(stage3_bg)
ax.text(14, 16.4, 'STAGE 3: FINAL ASSEMBLY', fontsize=14, fontweight='bold',
        ha='center', va='center', color=C_HEADER, zorder=5)
ax.text(14, 16.1, 'dbt/models/silver/clean_store_prices.sql',
        fontsize=9, ha='center', va='center', color='#616161', zorder=5)

# Inputs
draw_db(ax, 2, 14.2, 3.5, 0.8, 'int_prices_cleaned\n+ int_coicop_classified', '#BBDEFB', '#1565C0', 7)
draw_db(ax, 6.5, 14.2, 3.5, 0.8, 'Overrides + AI Cache\n+ Category Map', C_OPS, C_OPS_BORDER, 7)

# Coalesce priority
draw_box(ax, 11, 10.5, 15.5, 5.0, '', C_WHITE, C_SILVER_BORDER, linewidth=1.5)
ax.text(18.75, 15.2, 'COICOP COALESCE PRIORITY', fontsize=10, fontweight='bold',
        ha='center', va='center', color=C_HEADER, zorder=5)

priorities = [
    '1. int_coicop_classified.coicop_division',
    '2. Override barcode match (ov_barcode)',
    '3. Override name+store match (ov_name_store)',
    '4. Store domain hardcodes (khmer24→04, etc.)',
    '5. Override name global match (ov_name_global)',
    '6. AI cache match (confidence >= 0.50)',
    '7. Category map match',
    '8. Store defaults',
    '9. UNCLASSIFIED fallback',
]
for i, p in enumerate(priorities):
    ax.text(11.5, 14.7 - i * 0.45, p, fontsize=8, ha='left', va='center',
            color=C_TEXT, zorder=5)

# Filter note
ax.text(18.75, 10.9, 'FILTER: price_khr > 0', fontsize=8, fontweight='bold',
        ha='center', va='center', color='#C62828', zorder=5)

# Output: THE main silver table
draw_db(ax, 2, 10.5, 7.5, 1.5, 'silver.clean_store_prices\n(raw_price_id PK, scrape_date, store_slug, item_id,\nprice_khr, coicop_division, coicop_code, coicop_method,\ncoicop_confidence, is_outlier, cpi_eligible)',
        '#C8E6C9', C_SILVER_BORDER, 7)

# Arrows
draw_arrow(ax, 3.75, 14.2, 3.75, 12.0, C_SILVER_BORDER, 2)
draw_arrow(ax, 8.25, 14.2, 6, 12.0, C_SILVER_BORDER, 2)
draw_arrow(ax, 11, 13.0, 9.5, 11.5, C_SILVER_BORDER, 2)

# ═══════════════════════════════════════════════════════════════════════
# STAGE 4: HEDONIC ADJUSTMENT
# ═══════════════════════════════════════════════════════════════════════
stage4_bg = FancyBboxPatch((1, 4.5), 12.5, 5.2, boxstyle='round,pad=0.1',
                            facecolor='#F3E5F5', edgecolor='#8E24AA',
                            linewidth=2, alpha=0.3, zorder=0)
ax.add_patch(stage4_bg)
ax.text(7.25, 9.4, 'STAGE 4: HEDONIC ADJUSTMENT', fontsize=12, fontweight='bold',
        ha='center', va='center', color='#4A148C', zorder=5)
ax.text(7.25, 9.1, 'pipeline/hedonic_regression.py',
        fontsize=8, ha='center', va='center', color='#616161', zorder=5)

# Hedonic process
draw_box(ax, 1.5, 5.0, 11.5, 3.8, '', C_WHITE, '#8E24AA', linewidth=1)
hedonic_steps = [
    'Fetch Division 08/09 items (trailing 3 months)',
    'Extract features: RAM_GB, Storage_GB, Screen, Camera, 5G',
    'Fit OLS: ln(price) ~ RAM + Storage + Screen + Camera + 5G',
    'Baseline = previous month avg specs',
    'hedonic_adjusted = raw × exp(ln_pred_base - ln_pred_item)',
]
for i, s in enumerate(hedonic_steps):
    ax.text(2.0, 8.3 - i * 0.6, f'{i+1}. {s}', fontsize=7.5, ha='left', va='center',
            color=C_TEXT, zorder=5)

# Hedonic output
draw_db(ax, 1.5, 4.8, 5.5, 0.7, 'silver.hedonic_adjusted_prices\n(raw→hedonic adjusted prices)',
        '#E1BEE7', '#8E24AA', 7)

# ═══════════════════════════════════════════════════════════════════════
# STAGE 5: OPERATIONAL TABLES
# ═══════════════════════════════════════════════════════════════════════
stage5_bg = FancyBboxPatch((14, 4.5), 13, 5.2, boxstyle='round,pad=0.1',
                            facecolor='#FFF3E0', edgecolor='#E65100',
                            linewidth=2, alpha=0.3, zorder=0)
ax.add_patch(stage5_bg)
ax.text(20.5, 9.4, 'STAGE 5: OPERATIONAL TABLES', fontsize=12, fontweight='bold',
        ha='center', va='center', color='#BF360C', zorder=5)
ax.text(20.5, 9.1, 'silver.* schema control tables',
        fontsize=8, ha='center', va='center', color='#616161', zorder=5)

ops_tables = [
    'silver.coicop_override (seed rules)',
    'silver.coicop_override_manual (operator)',
    'silver.coicop_category_map (store→div)',
    'silver.classification_queue (triage)',
    'silver.dim_coicop_ai_cache (AI memo)',
    'silver.classification_ground_truth',
    'silver.item_embedding_cache (768-dim)',
    'silver.dim_canonical_products (SKU link)',
]
for i, t in enumerate(ops_tables):
    ax.text(14.5, 8.6 - i * 0.45, f'• {t}', fontsize=7.5, ha='left', va='center',
            color=C_TEXT, zorder=5)

# ═══════════════════════════════════════════════════════════════════════
# OUTPUT: FEEDS INTO GOLD
# ═══════════════════════════════════════════════════════════════════════
output_bg = FancyBboxPatch((1, 2.0), 26, 2.2, boxstyle='round,pad=0.1',
                            facecolor='#FFF8E1', edgecolor='#F57F17',
                            linewidth=2, alpha=0.4, zorder=0)
ax.add_patch(output_bg)
ax.text(14, 3.9, 'OUTPUT → GOLD LAYER', fontsize=14, fontweight='bold',
        ha='center', va='center', color='#E65100', zorder=5)

draw_db(ax, 2, 2.2, 4.5, 0.9, 'gold.dim_items\n(item_id PK, canonical_name,\ncoicop_division)', C_GOLD, C_GOLD_BORDER, 7)
draw_db(ax, 7.5, 2.2, 4.5, 0.9, 'gold.dim_stores\n(store_slug PK, store_name,\ndefault_coicop_division)', C_GOLD, C_GOLD_BORDER, 7)
draw_db(ax, 13, 2.2, 5.5, 0.9, 'gold.fct_daily_prices\n(scrape_date, store_slug, item_id,\nprice_khr, unit_price_khr)', C_GOLD, C_GOLD_BORDER, 7)
draw_db(ax, 19.5, 2.2, 6, 0.9, 'gold.fct_elementary_indices\n+ gold.fct_cpi_daily\n(Jevons + Laspeyres)', C_GOLD, C_GOLD_BORDER, 7)

# Main arrows from clean_store_prices to gold
draw_arrow(ax, 5.75, 10.5, 4.25, 3.1, C_GOLD_BORDER, 2.5)
draw_arrow(ax, 5.75, 10.5, 9.75, 3.1, C_GOLD_BORDER, 2.5)
draw_arrow(ax, 5.75, 10.5, 15.75, 3.1, C_GOLD_BORDER, 2.5)
draw_arrow(ax, 5.75, 10.5, 22.5, 3.1, C_GOLD_BORDER, 2.5)

# ═══════════════════════════════════════════════════════════════════════
# DAG ORCHESTRATION SIDEBAR
# ═══════════════════════════════════════════════════════════════════════
dag_bg = FancyBboxPatch((0.2, 10.0), 4.5, 6.7, boxstyle='round,pad=0.1',
                         facecolor='#ECEFF1', edgecolor='#455A64',
                         linewidth=1.5, alpha=0.6, zorder=0)
ax.add_patch(dag_bg)
ax.text(2.45, 16.4, 'AIRFLOW DAG', fontsize=10, fontweight='bold',
        ha='center', va='center', color='#263238', zorder=5)
ax.text(2.45, 16.05, 'silver_dag.py', fontsize=8,
        ha='center', va='center', color='#616161', zorder=5)

dag_steps = [
    ('silver_item_matching', '#C8E6C9'),
    ('gemini_item_auto_review', '#DCEDC8'),
    ('dbt_seed', '#BBDEFB'),
    ('gemini_coicop', '#FFF9C4'),
    ('hedonic_adjustment', '#E1BEE7'),
    ('dbt_silver_run', '#C8E6C9'),
    ('dbt_silver_test', '#A5D6A7'),
]
for i, (step, color) in enumerate(dag_steps):
    y_pos = 15.5 - i * 0.7
    draw_box(ax, 0.5, y_pos, 3.8, 0.55, step, color, '#455A64', 7, fontweight='bold')
    if i < len(dag_steps) - 1:
        draw_arrow(ax, 2.45, y_pos, 2.45, y_pos + 0.15, '#455A64', 1)

# Parallel indicator
ax.annotate('', xy=(1.5, 13.45), xytext=(3.4, 13.45),
            arrowprops=dict(arrowstyle='<->', color='#455A64', lw=1.5), zorder=5)
ax.text(2.45, 13.7, 'parallel', fontsize=6, ha='center', va='center',
        color='#455A64', zorder=5, style='italic')

# ═══════════════════════════════════════════════════════════════════════
# LEGEND
# ═══════════════════════════════════════════════════════════════════════
legend_items = [
    (C_BRONZE, C_BRONZE_BORDER, 'Bronze (Raw)'),
    (C_SILVER, C_SILVER_BORDER, 'Silver (Clean)'),
    (C_GOLD, C_GOLD_BORDER, 'Gold (Analytical)'),
    (C_HEDONIC, C_HEDONIC_BORDER, 'Hedonic'),
    (C_OPS, C_OPS_BORDER, 'Operational'),
]
for i, (color, border, label) in enumerate(legend_items):
    x = 2 + i * 4.5
    draw_box(ax, x, 0.3, 1.2, 0.5, '', color, border, linewidth=2)
    ax.text(x + 1.4, 0.55, label, fontsize=8, ha='left', va='center',
            color=C_TEXT, zorder=5)

# Source code references
ax.text(14, 0.05, 'Source: pipeline/item_matcher.py, vector_item_matcher.py, hybrid_embeddings_classifier.py, '
        'hedonic_regression.py, text_clean.py | dbt/models/silver/*.sql | dbt/macros/*.sql | sql/schema.sql | orchestration/dags/silver_dag.py',
        fontsize=6.5, ha='center', va='center', color='#9E9E9E', zorder=5, style='italic')

# ═══════════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════════
output_path = r'D:\CPI PIPELINE\docs\diagrams\silver_layer_architecture.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(),
            edgecolor='none', pad_inches=0.3)
plt.close()
print(f"Diagram saved to: {output_path}")
