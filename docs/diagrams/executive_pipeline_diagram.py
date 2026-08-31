"""
Cambodia Daily CPI Pipeline — Executive Enterprise Architecture Infographic
World-class modern tech design • Pure White Background (#FFFFFF) • Floating Card UI Aesthetics
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ═══════════════════════════════════════════════════════════════════════
# CANVAS CONFIGURATION (Landscape 16:10 format)
# ═══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(1, 1, figsize=(18, 11))
ax.set_xlim(0, 20)
ax.set_ylim(0, 12.2)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#FFFFFF')

# ── Color Palette (Modern Enterprise Data Platform) ──
C_WHITE = '#FFFFFF'
C_DARK_NAVY = '#0F172A'
C_SLATE = '#334155'
C_MUTED = '#64748B'
C_LIGHT_BORDER = '#E2E8F0'

# Pillar Accent Colors
COL_BRONZE = '#0284C7'   # Sky Blue
COL_BRONZE_BG = '#F0F9FF'
COL_SILVER = '#4F46E5'   # Indigo
COL_SILVER_BG = '#EEF2FF'
COL_GOLD = '#D97706'     # Amber / Gold
COL_GOLD_BG = '#FFFBEB'
COL_SERVING = '#0D9488'  # Emerald / Teal
COL_SERVING_BG = '#F0FDFA'


def draw_card_container(ax, x, y, w, h, bg_color, border_color, title, subtitle, step_num, accent_color):
    """Draws a premium floating card with an accent header bar and step badge."""
    card = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.03', facecolor=C_WHITE,
                          edgecolor=border_color, linewidth=1.5, zorder=2)
    ax.add_patch(card)
    
    # Top Header Banner
    header_h = 1.05
    header_box = FancyBboxPatch((x, y + h - header_h), w, header_h, boxstyle='round,pad=0.03',
                                facecolor=bg_color, edgecolor=border_color, linewidth=1.2, zorder=3)
    ax.add_patch(header_box)
    
    # Accent Top Strip
    strip = FancyBboxPatch((x + 0.15, y + h - 0.10), w - 0.3, 0.07, boxstyle='round,pad=0.01',
                           facecolor=accent_color, edgecolor='none', zorder=4)
    ax.add_patch(strip)
    
    # Step Badge
    badge_w, badge_h = 0.95, 0.34
    badge = FancyBboxPatch((x + 0.25, y + h - 0.60), badge_w, badge_h, boxstyle='round,pad=0.02',
                           facecolor=accent_color, edgecolor='none', zorder=5)
    ax.add_patch(badge)
    ax.text(x + 0.25 + badge_w/2, y + h - 0.60 + badge_h/2, f"STEP {step_num}",
            fontsize=6.8, fontweight='bold', ha='center', va='center', color=C_WHITE, zorder=6)
    
    # Header Titles
    ax.text(x + 1.35, y + h - 0.45, title, fontsize=8.5, fontweight='bold',
            ha='left', va='center', color=C_DARK_NAVY, zorder=5)
    ax.text(x + 1.35, y + h - 0.76, subtitle, fontsize=6.5, fontweight='normal',
            ha='left', va='center', color=C_MUTED, zorder=5)


def draw_sub_block(ax, x, y, w, h, icon_tag, title, items, tag_text, tag_color, tag_bg):
    """Draws an inner component block with an icon chip and bullets."""
    box = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02', facecolor='#F8FAFC',
                         edgecolor='#E2E8F0', linewidth=1.0, zorder=3)
    ax.add_patch(box)
    
    # Icon Badge Chip
    chip_w, chip_h = 0.65, 0.32
    chip = FancyBboxPatch((x + 0.2, y + h - 0.44), chip_w, chip_h, boxstyle='round,pad=0.01',
                          facecolor=tag_bg, edgecolor=tag_color, linewidth=0.8, zorder=4)
    ax.add_patch(chip)
    ax.text(x + 0.2 + chip_w/2, y + h - 0.44 + chip_h/2, icon_tag,
            fontsize=5.8, fontweight='bold', ha='center', va='center', color=tag_color, zorder=5)
    
    # Title
    ax.text(x + 0.95, y + h - 0.28, title, fontsize=7.2, fontweight='bold',
            ha='left', va='center', color=C_DARK_NAVY, zorder=5)
    
    # Bullets
    for bi, item in enumerate(items):
        ax.text(x + 0.25, y + h - 0.60 - (bi * 0.25), f"• {item}", fontsize=5.8,
                ha='left', va='center', color=C_SLATE, zorder=5)
    
    # Bottom Tag Pill
    if tag_text:
        tw = w - 0.4
        th = 0.26
        tbox = FancyBboxPatch((x + 0.2, y + 0.10), tw, th, boxstyle='round,pad=0.01',
                              facecolor=tag_bg, edgecolor='none', zorder=4)
        ax.add_patch(tbox)
        ax.text(x + 0.2 + tw/2, y + 0.10 + th/2, tag_text, fontsize=5.5, fontweight='bold',
                ha='center', va='center', color=tag_color, zorder=5)


def draw_pipe_flow(ax, x1, y1, x2, y2, color):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=2.2,
                               connectionstyle='arc3,rad=0', mutation_scale=14), zorder=6)


# ═══════════════════════════════════════════════════════════════════════
# TOP BRANDING HEADER
# ═══════════════════════════════════════════════════════════════════════
top_pill = FancyBboxPatch((7.2, 11.55), 5.6, 0.38, boxstyle='round,pad=0.02',
                          facecolor='#F0FDFA', edgecolor='#0D9488', linewidth=1.1, zorder=3)
ax.add_patch(top_pill)
ax.text(10, 11.74, 'NATIONAL BANK OF CAMBODIA • NIS STANDARDS COMPLIANT', fontsize=7.2,
        fontweight='bold', ha='center', va='center', color='#0F766E', zorder=4)

ax.text(10, 11.15, 'Cambodia Daily Consumer Price Index (CPI)', fontsize=18,
        fontweight='bold', ha='center', va='center', color=C_DARK_NAVY, zorder=5)
ax.text(10, 10.75, 'End-to-End Medallion Data Engineering & Real-Time Inflation Intelligence Platform',
        fontsize=8.2, ha='center', va='center', color=C_MUTED, zorder=5)

# Metrics Strip
metrics = [
    ("20+", "Retail Sources"),
    ("Daily", "Scrape Cadence"),
    ("768-dim", "Vectors"),
    ("12", "COICOP Divisions"),
    ("T+0", "ML Flash Nowcast"),
    ("100%", "Airflow Automated")
]
for mi, (m_val, m_lbl) in enumerate(metrics):
    mx = 1.1 + mi * 3.05
    m_box = FancyBboxPatch((mx, 10.05), 2.7, 0.45, boxstyle='round,pad=0.02',
                           facecolor='#F8FAFC', edgecolor='#E2E8F0', linewidth=1.0, zorder=2)
    ax.add_patch(m_box)
    ax.text(mx + 0.65, 10.27, m_val, fontsize=7.8, fontweight='bold', ha='center', va='center', color='#0284C7', zorder=4)
    ax.text(mx + 1.65, 10.27, m_lbl, fontsize=5.8, fontweight='bold', ha='center', va='center', color=C_SLATE, zorder=4)

ax.plot([0.8, 19.2], [9.85, 9.85], color=C_LIGHT_BORDER, linewidth=1.2, zorder=1)


# ═══════════════════════════════════════════════════════════════════════
# 4 MAIN MEDALLION PILLARS (Columns 01 to 04)
# ═══════════════════════════════════════════════════════════════════════
col_w = 4.35
col_h = 7.1
col_y = 2.4
col_xs = [0.8, 5.5, 10.2, 14.85]

# ─────────────────────────────────────────────────────────────────────
# PILLAR 1: BRONZE LAYER (Ingestion)
# ─────────────────────────────────────────────────────────────────────
draw_card_container(ax, col_xs[0], col_y, col_w, col_h, COL_BRONZE_BG, COL_BRONZE,
                    "BRONZE LAYER", "Raw Ingestion & Circuit Breakers", "01", COL_BRONZE)

draw_sub_block(ax, col_xs[0] + 0.2, col_y + 3.85, col_w - 0.4, 2.05,
               "SRC", "Multi-Channel Scrapers",
               ["Supermarkets: AEON 1&3, DeliShop",
                "Pharma & Tech: Community, Samnang",
                "Transit & Fuel: redBus, MOC Gas",
                "Official FX: MEF USD/KHR Daily"],
               "scrapers/sources.py", "#0369A1", "#E0F2FE")

draw_sub_block(ax, col_xs[0] + 0.2, col_y + 1.85, col_w - 0.4, 1.85,
               "VAL", "Ingestion Guards",
               ["Zero-count circuit breaker",
                "Schema payload validation",
                "Dedup on (store, sku, date)",
                "Error isolation queue"],
               "pipeline/canonical.py", "#0369A1", "#E0F2FE")

draw_sub_block(ax, col_xs[0] + 0.2, col_y + 0.20, col_w - 0.4, 1.50,
               "DB", "Raw Bronze Tables",
               ["bronze.raw_prices (JSONB)",
                "staging.raw_scrapes"],
               "PostgreSQL 16 Storage", "#0C4A6E", "#BAE6FD")


# ─────────────────────────────────────────────────────────────────────
# PILLAR 2: SILVER LAYER (Clean & Resolve)
# ─────────────────────────────────────────────────────────────────────
draw_card_container(ax, col_xs[1], col_y, col_w, col_h, COL_SILVER_BG, COL_SILVER,
                    "SILVER LAYER", "Vector Matching & COICOP Ladder", "02", COL_SILVER)

draw_sub_block(ax, col_xs[1] + 0.2, col_y + 3.85, col_w - 0.4, 2.05,
               "VEC", "Vector Item Matcher",
               ["768-dim Cosine Similarity",
                "Deterministic Spec Guards",
                "3-Key Gemini AI Arbitrator",
                "UUID Canonical Identity"],
               "silver.canonical_items", "#3730A3", "#E0E7FF")

draw_sub_block(ax, col_xs[1] + 0.2, col_y + 1.85, col_w - 0.4, 1.85,
               "CLS", "4-Tier COICOP Engine",
               ["Tier 1: Authority Overrides",
                "Tier 2: 15 Pure Store Locks",
                "Tier 3: 768-dim Vector Embed",
                "Tier 4: Gemini Pro Cache"],
               "staging.int_coicop_classified", "#3730A3", "#E0E7FF")

draw_sub_block(ax, col_xs[1] + 0.2, col_y + 0.20, col_w - 0.4, 1.50,
               "TBL", "Conformed Daily Facts",
               ["silver.clean_store_prices",
                "silver.hedonic_adjusted_prices"],
               "dbt Core Incremental", "#312E81", "#C7D2FE")


# ─────────────────────────────────────────────────────────────────────
# PILLAR 3: GOLD LAYER (Star Schema & Econometrics)
# ─────────────────────────────────────────────────────────────────────
draw_card_container(ax, col_xs[2], col_y, col_w, col_h, COL_GOLD_BG, COL_GOLD,
                    "GOLD LAYER", "Star Schema & Econometric Math", "03", COL_GOLD)

draw_sub_block(ax, col_xs[2] + 0.2, col_y + 3.85, col_w - 0.4, 2.05,
               "DIM", "Kimball Star Schema",
               ["gold.dim_items (Master UUID)",
                "gold.dim_stores (Store Directory)",
                "gold.fct_daily_prices (Fact)",
                "Strict C2 positive-price filter"],
               "dbt Dimensional Mart", "#92400E", "#FEF3C7")

draw_sub_block(ax, col_xs[2] + 0.2, col_y + 1.85, col_w - 0.4, 1.85,
               "IDX", "CPI Calculation Engine",
               ["Jevons Geometric Mean Index",
                "7-Day carryover imputation",
                "12-Division Laspeyres weights",
                "NIS Cambodia expenditure shares"],
               "pipeline/cpi_calculator.py", "#92400E", "#FEF3C7")

draw_sub_block(ax, col_xs[2] + 0.2, col_y + 0.20, col_w - 0.4, 1.50,
               "OUT", "Published Daily Indices",
               ["gold.fct_cpi_daily (Headline)",
                "gold.fct_elementary_indices"],
               "Official Daily Output", "#78350F", "#FDE68A")


# ─────────────────────────────────────────────────────────────────────
# PILLAR 4: SERVING & ANALYTICS (Actionable Outputs)
# ─────────────────────────────────────────────────────────────────────
draw_card_container(ax, col_xs[3], col_y, col_w, col_h, COL_SERVING_BG, COL_SERVING,
                    "SERVING & ML", "Nowcasting, BI & Observability", "04", COL_SERVING)

draw_sub_block(ax, col_xs[3] + 0.2, col_y + 3.85, col_w - 0.4, 2.05,
               "ML", "ML Flash Nowcasting",
               ["LightGBM & XGBoost Models",
                "7d, 14d, 30d momentum features",
                "Food & Fuel early signals",
                "T+0 Real-Time Flash Forecast"],
               "gold.fct_ml_nowcast_features", "#115E59", "#CCFBF1")

draw_sub_block(ax, col_xs[3] + 0.2, col_y + 1.85, col_w - 0.4, 1.85,
               "VIS", "Executive BI & Alerts",
               ["Power BI Live CPI Tracker",
                "Metabase v0.49 Health Matrix",
                "Telegram Bot Daily Alerts",
                "Automated Anomaly SLA feeds"],
               "Executive Dashboards", "#115E59", "#CCFBF1")

draw_sub_block(ax, col_xs[3] + 0.2, col_y + 0.20, col_w - 0.4, 1.50,
               "GOV", "Monetary Policy Value",
               ["Policy Makers & Central Bank",
                "High-Frequency Macro Telemetry"],
               "REST API & PDF Briefings", "#134E4A", "#99F6E4")


# ═══════════════════════════════════════════════════════════════════════
# PIPE FLOW CONNECTORS
# ═══════════════════════════════════════════════════════════════════════
draw_pipe_flow(ax, col_xs[0] + col_w + 0.04, col_y + col_h/2, col_xs[1] - 0.04, col_y + col_h/2, COL_BRONZE)
draw_pipe_flow(ax, col_xs[1] + col_w + 0.04, col_y + col_h/2, col_xs[2] - 0.04, col_y + col_h/2, COL_SILVER)
draw_pipe_flow(ax, col_xs[2] + col_w + 0.04, col_y + col_h/2, col_xs[3] - 0.04, col_y + col_h/2, COL_GOLD)


# ═══════════════════════════════════════════════════════════════════════
# BOTTOM PLATFORM INFRASTRUCTURE BAR
# ═══════════════════════════════════════════════════════════════════════
infra_box = FancyBboxPatch((0.8, 0.45), 18.4, 1.55, boxstyle='round,pad=0.03',
                           facecolor='#F8FAFC', edgecolor='#CBD5E1', linewidth=1.2, zorder=2)
ax.add_patch(infra_box)

ax.text(1.1, 1.68, 'CORE PLATFORM INFRASTRUCTURE & ORCHESTRATION BACKBONE',
        fontsize=7.5, fontweight='bold', color=C_DARK_NAVY, zorder=4)

infra_items = [
    ("Apache Airflow 2.10", "cpi_master_dag • silver • gold", "#0284C7", "#E0F2FE"),
    ("PostgreSQL 16 DB", "cpi_db multi-schema storage", "#4F46E5", "#EEF2FF"),
    ("dbt Core Engine", "Modular SQL & automated tests", "#EA580C", "#FFEDD5"),
    ("Gemini 2.5 3-Key Pool", "45 RPM • Auto-failover rotation", "#7C3AED", "#EDE9FE"),
    ("Docker Compose", "Isolated container architecture", "#0D9488", "#CCFBF1"),
]

for ii, (ititle, isub, icol, ibg) in enumerate(infra_items):
    ix = 1.05 + ii * 3.65
    ibox = FancyBboxPatch((ix, 0.60), 3.5, 0.85, boxstyle='round,pad=0.02',
                          facecolor=C_WHITE, edgecolor=icol, linewidth=1.1, zorder=3)
    ax.add_patch(ibox)
    ax.text(ix + 1.75, 1.15, ititle, fontsize=6.8, fontweight='bold', ha='center', va='center', color=icol, zorder=4)
    ax.text(ix + 1.75, 0.85, isub, fontsize=5.5, ha='center', va='center', color=C_MUTED, zorder=4)


# ═══════════════════════════════════════════════════════════════════════
# SAVE TO DISK
# ═══════════════════════════════════════════════════════════════════════
output_path = r'D:\CPI PIPELINE\docs\diagrams\cpi_pipeline_executive_design.png'
plt.savefig(output_path, dpi=115, bbox_inches='tight', facecolor='#FFFFFF', edgecolor='none', pad_inches=0.3)
plt.close()
print(f"[SUCCESS] Executive Design Architecture Diagram rendered to: {output_path}")
