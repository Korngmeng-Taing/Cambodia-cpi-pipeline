"""
Cambodia Daily CPI Pipeline — End-to-End Architecture Diagram
A modern, high-design visual infographic showcasing the entire pipeline with a pure white background (#FFFFFF).
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ═══════════════════════════════════════════════════════════════════════
# CANVAS SETUP (Pure White Background, Memory-Optimized)
# ═══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(1, 1, figsize=(16, 9.6))
ax.set_xlim(0, 20)
ax.set_ylim(0, 12)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#FFFFFF')

# ── Color Palette (Modern, Vibrant, High-Contrast) ──
C_WHITE = '#FFFFFF'
C_DARK = '#0F172A'
C_MUTED = '#64748B'

THEMES = {
    "bronze": {
        "border": "#0284C7", "bg": "#F0F9FF", "header_bg": "#0284C7",
        "card_bg": "#FFFFFF", "pill_bg": "#E0F2FE", "pill_text": "#0369A1", "num": "01"
    },
    "silver": {
        "border": "#4F46E5", "bg": "#EEF2FF", "header_bg": "#4F46E5",
        "card_bg": "#FFFFFF", "pill_bg": "#E0E7FF", "pill_text": "#3730A3", "num": "02"
    },
    "gold": {
        "border": "#D97706", "bg": "#FFFBEB", "header_bg": "#D97706",
        "card_bg": "#FFFFFF", "pill_bg": "#FEF3C7", "pill_text": "#92400E", "num": "03"
    },
    "serving": {
        "border": "#0D9488", "bg": "#F0FDFA", "header_bg": "#0D9488",
        "card_bg": "#FFFFFF", "pill_bg": "#CCFBF1", "pill_text": "#115E59", "num": "04"
    }
}


def draw_box(ax, x, y, w, h, bg=C_WHITE, border='#CBD5E1', lw=1.4, zorder=2, pad=0.03):
    box = FancyBboxPatch((x, y), w, h, boxstyle=f'round,pad={pad}', facecolor=bg,
                         edgecolor=border, linewidth=lw, zorder=zorder)
    ax.add_patch(box)


def draw_pill(ax, x, y, w, h, text, bg='#E2E8F0', text_col='#0F172A', border=None, fontsize=7.2, fontweight='bold', zorder=4):
    b_col = border if border else bg
    draw_box(ax, x, y, w, h, bg=bg, border=b_col, lw=1.0, zorder=zorder, pad=0.02)
    ax.text(x + w/2, y + h/2, text, fontsize=fontsize, fontweight=fontweight,
            ha='center', va='center', color=text_col, zorder=zorder+1)


def draw_arrow(ax, x1, y1, x2, y2, color='#64748B', lw=1.8, zorder=5):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                               connectionstyle='arc3,rad=0', mutation_scale=13), zorder=zorder)


# ═══════════════════════════════════════════════════════════════════════
# HEADER & BRANDING (Pure White Theme)
# ═══════════════════════════════════════════════════════════════════════
ax.text(10, 11.4, 'NATIONAL BANK OF CAMBODIA • NIS COMPLIANT ARCHITECTURE', fontsize=8.5, fontweight='bold',
        ha='center', va='center', color='#0F766E', zorder=5)
ax.text(10, 10.95, 'Cambodia Daily Consumer Price Index (CPI) Pipeline', fontsize=18, fontweight='bold',
        ha='center', va='center', color='#0F172A', zorder=5)
ax.text(10, 10.55, 'End-to-End Medallion Data Platform: Ingestion → Vector Resolution → COICOP Index Engine → ML Nowcasting',
        fontsize=8.8, ha='center', va='center', color='#64748B', zorder=5)

ax.plot([0.8, 19.2], [10.25, 10.25], color='#E2E8F0', linewidth=1.5, zorder=1)


# ═══════════════════════════════════════════════════════════════════════
# 4 MAIN MEDALLION PILLARS (Columns 01 to 04)
# ═══════════════════════════════════════════════════════════════════════
col_w = 4.4
col_h = 7.4
col_y = 2.5
col_xs = [0.8, 5.5, 10.2, 14.9]

# ─────────────────────────────────────────────────────────────────────
# COLUMN 1: BRONZE LAYER (Raw Ingestion)
# ─────────────────────────────────────────────────────────────────────
cfg1 = THEMES["bronze"]
cx1 = col_xs[0]
draw_box(ax, cx1, col_y, col_w, col_h, bg=cfg1["bg"], border=cfg1["border"], lw=1.8, zorder=2)

draw_pill(ax, cx1 + 0.3, col_y + col_h - 0.65, col_w - 0.6, 0.45, "01 • BRONZE LAYER (RAW)",
          bg=cfg1["header_bg"], text_col=C_WHITE, fontsize=7.8)

# Card 1.1: 20 Retail Sources
draw_box(ax, cx1 + 0.25, col_y + 4.5, col_w - 0.5, 2.1, bg=C_WHITE, border='#BAE6FD', lw=1.2, zorder=3)
ax.text(cx1 + 0.4, col_y + 6.3, '20+ Retail Scrapers', fontsize=7.8, fontweight='bold', color='#0369A1', zorder=4)
s_text = (
    "• Supermarkets: AEON 1 & 3, DeliShop\n"
    "• Pharma & Tech: Community, Samnang, Ary\n"
    "• Transport & Hotels: redBus, Sokha, Hyatt\n"
    "• Utilities & Fuel: MOC Gas, EDC, Housing\n"
    "• Official FX: MEF Daily Exchange Rates"
)
ax.text(cx1 + 0.4, col_y + 5.35, s_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 1.2: Validation & Circuit Breaker
draw_box(ax, cx1 + 0.25, col_y + 2.45, col_w - 0.5, 1.85, bg=C_WHITE, border='#BAE6FD', lw=1.2, zorder=3)
ax.text(cx1 + 0.4, col_y + 3.95, 'Circuit Breaker & Validation', fontsize=7.8, fontweight='bold', color='#0369A1', zorder=4)
v_text = (
    "• Zero-count anomaly circuit breaker\n"
    "• Schema v1.0 payload standardizer\n"
    "• Dedup guard on (store, sku, date)\n"
    "• Error audit in bronze.scrape_errors"
)
ax.text(cx1 + 0.4, col_y + 3.15, v_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 1.3: Raw Tables Badge
draw_box(ax, cx1 + 0.25, col_y + 0.3, col_w - 0.5, 1.95, bg='#E0F2FE', border=cfg1["border"], lw=1.2, zorder=3)
ax.text(cx1 + col_w/2, col_y + 1.9, 'PostgreSQL Bronze Tables', fontsize=7.5, fontweight='bold', ha='center', color='#0369A1', zorder=4)
ax.text(cx1 + col_w/2, col_y + 1.4, 'bronze.raw_prices\n(raw_price_id PK, payload JSONB)', fontsize=6.2, ha='center', color='#0C4A6E', zorder=4)
ax.text(cx1 + col_w/2, col_y + 0.7, 'staging.raw_scrapes • staging.exchange_rates', fontsize=6.2, ha='center', color='#0369A1', fontweight='bold', zorder=4)


# ─────────────────────────────────────────────────────────────────────
# COLUMN 2: SILVER LAYER (Clean & Resolve)
# ─────────────────────────────────────────────────────────────────────
cfg2 = THEMES["silver"]
cx2 = col_xs[1]
draw_box(ax, cx2, col_y, col_w, col_h, bg=cfg2["bg"], border=cfg2["border"], lw=1.8, zorder=2)

draw_pill(ax, cx2 + 0.3, col_y + col_h - 0.65, col_w - 0.6, 0.45, "02 • SILVER LAYER (RESOLVE)",
          bg=cfg2["header_bg"], text_col=C_WHITE, fontsize=7.8)

# Card 2.1: Vector Item Matching
draw_box(ax, cx2 + 0.25, col_y + 4.5, col_w - 0.5, 2.1, bg=C_WHITE, border='#C7D2FE', lw=1.2, zorder=3)
ax.text(cx2 + 0.4, col_y + 6.3, 'Vector Item Matcher (Stage 0)', fontsize=7.8, fontweight='bold', color='#3730A3', zorder=4)
m_text = (
    "• 768-dim Vector Cosine Similarity\n"
    "• Deterministic Spec Guards (RAM, Storage)\n"
    "• 3-Key Gemini Pro/Flash Arbitrator\n"
    "• silver.canonical_items (UUID PK)\n"
    "• silver.item_match_log (Audit Trail)"
)
ax.text(cx2 + 0.4, col_y + 5.35, m_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 2.2: Hygiene & COICOP Ladder
draw_box(ax, cx2 + 0.25, col_y + 2.45, col_w - 0.5, 1.85, bg=C_WHITE, border='#C7D2FE', lw=1.2, zorder=3)
ax.text(cx2 + 0.4, col_y + 3.95, 'Hygiene & 4-Tier COICOP', fontsize=7.8, fontweight='bold', color='#3730A3', zorder=4)
h_text = (
    "• USD to KHR MEF daily FX conversion\n"
    "• Khmer numerals (0-9) & unit norm\n"
    "• 15 Pure Store Domain Locks (<0.01ms)\n"
    "• Gemini AI memoized classification"
)
ax.text(cx2 + 0.4, col_y + 3.15, h_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 2.3: Clean Store Prices Table
draw_box(ax, cx2 + 0.25, col_y + 0.3, col_w - 0.5, 1.95, bg='#E0E7FF', border=cfg2["border"], lw=1.2, zorder=3)
ax.text(cx2 + col_w/2, col_y + 1.9, 'Conformed Clean Fact Table', fontsize=7.5, fontweight='bold', ha='center', color='#3730A3', zorder=4)
ax.text(cx2 + col_w/2, col_y + 1.35, 'silver.clean_store_prices\n(Clean KHR Prices, COICOP Codes, Units)', fontsize=6.2, ha='center', color='#312E81', zorder=4)
ax.text(cx2 + col_w/2, col_y + 0.7, 'silver.hedonic_adjusted_prices (Div 08/09)', fontsize=6.2, ha='center', color='#4338CA', fontweight='bold', zorder=4)


# ─────────────────────────────────────────────────────────────────────
# COLUMN 3: GOLD LAYER (Star Schema & Econometrics)
# ─────────────────────────────────────────────────────────────────────
cfg3 = THEMES["gold"]
cx3 = col_xs[2]
draw_box(ax, cx3, col_y, col_w, col_h, bg=cfg3["bg"], border=cfg3["border"], lw=1.8, zorder=2)

draw_pill(ax, cx3 + 0.3, col_y + col_h - 0.65, col_w - 0.6, 0.45, "03 • GOLD LAYER (ECONOMETRICS)",
          bg=cfg3["header_bg"], text_col=C_WHITE, fontsize=7.8)

# Card 3.1: Kimball Star Schema
draw_box(ax, cx3 + 0.25, col_y + 4.5, col_w - 0.5, 2.1, bg=C_WHITE, border='#FDE68A', lw=1.2, zorder=3)
ax.text(cx3 + 0.4, col_y + 6.3, 'Kimball Dimensional Model', fontsize=7.8, fontweight='bold', color='#B45309', zorder=4)
g_text = (
    "• gold.dim_items (Canonical Master UUID)\n"
    "• gold.dim_stores (Store metadata & purity)\n"
    "• gold.fct_daily_prices (Conformed Facts)\n"
    "• Grain: (scrape_date, store_slug, item_id)\n"
    "• Zero-price exclusion (C2 Fix)"
)
ax.text(cx3 + 0.4, col_y + 5.35, g_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 3.2: Jevons & Laspeyres Math
draw_box(ax, cx3 + 0.25, col_y + 2.45, col_w - 0.5, 1.85, bg=C_WHITE, border='#FDE68A', lw=1.2, zorder=3)
ax.text(cx3 + 0.4, col_y + 3.95, 'CPI Index Calculation Engine', fontsize=7.8, fontweight='bold', color='#B45309', zorder=4)
idx_text = (
    "• Jevons geometric mean micro-index\n"
    "• 7-day missing price carryover imputation\n"
    "• 12-Division weighted Laspeyres aggregation\n"
    "• NIS Cambodia official expenditure weights"
)
ax.text(cx3 + 0.4, col_y + 3.15, idx_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 3.3: Final CPI Tables
draw_box(ax, cx3 + 0.25, col_y + 0.3, col_w - 0.5, 1.95, bg='#FEF3C7', border=cfg3["border"], lw=1.2, zorder=3)
ax.text(cx3 + col_w/2, col_y + 1.9, 'Published CPI Indices', fontsize=7.5, fontweight='bold', ha='center', color='#92400E', zorder=4)
ax.text(cx3 + col_w/2, col_y + 1.35, 'gold.fct_cpi_daily\n(National Headline & Core Daily Inflation)', fontsize=6.2, ha='center', color='#78350F', zorder=4)
ax.text(cx3 + col_w/2, col_y + 0.7, 'gold.fct_elementary_indices (Division Indices)', fontsize=6.2, ha='center', color='#B45309', fontweight='bold', zorder=4)


# ─────────────────────────────────────────────────────────────────────
# COLUMN 4: SERVING & ANALYTICS (Actionable Outputs)
# ─────────────────────────────────────────────────────────────────────
cfg4 = THEMES["serving"]
cx4 = col_xs[3]
draw_box(ax, cx4, col_y, col_w, col_h, bg=cfg4["bg"], border=cfg4["border"], lw=1.8, zorder=2)

draw_pill(ax, cx4 + 0.3, col_y + col_h - 0.65, col_w - 0.6, 0.45, "04 • SERVING & INTELLIGENCE",
          bg=cfg4["header_bg"], text_col=C_WHITE, fontsize=7.8)

# Card 4.1: ML Inflation Nowcasting
draw_box(ax, cx4 + 0.25, col_y + 4.5, col_w - 0.5, 2.1, bg=C_WHITE, border='#99F6E4', lw=1.2, zorder=3)
ax.text(cx4 + 0.4, col_y + 6.3, 'ML Inflation Nowcasting', fontsize=7.8, fontweight='bold', color='#0F766E', zorder=4)
ml_text = (
    "• LightGBM & XGBoost Real-Time Regressors\n"
    "• 7d, 14d, 30d momentum & volatility lags\n"
    "• Food (01) & Fuel (07) early signals\n"
    "• T+0 Flash CPI estimation (weeks ahead)\n"
    "• gold.fct_ml_nowcast_features"
)
ax.text(cx4 + 0.4, col_y + 5.35, ml_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 4.2: Dashboards & Alerts
draw_box(ax, cx4 + 0.25, col_y + 2.45, col_w - 0.5, 1.85, bg=C_WHITE, border='#99F6E4', lw=1.2, zorder=3)
ax.text(cx4 + 0.4, col_y + 3.95, 'Dashboards & Monitoring', fontsize=7.8, fontweight='bold', color='#0F766E', zorder=4)
bi_text = (
    "• Power BI / Streamlit Live Trackers\n"
    "• Metabase v0.49 20-source scraper matrix\n"
    "• Telegram Bot anomaly & daily run alerts\n"
    "• Automated SLA & price outlier monitoring"
)
ax.text(cx4 + 0.4, col_y + 3.15, bi_text, fontsize=6.2, color='#334155', linespacing=1.4, zorder=4)

# Card 4.3: Stakeholder Value
draw_box(ax, cx4 + 0.25, col_y + 0.3, col_w - 0.5, 1.95, bg='#CCFBF1', border=cfg4["border"], lw=1.2, zorder=3)
ax.text(cx4 + col_w/2, col_y + 1.9, 'Executive Insights & APIs', fontsize=7.5, fontweight='bold', ha='center', color='#115E59', zorder=4)
ax.text(cx4 + col_w/2, col_y + 1.35, 'Policy Makers & Financial Institutions\n(High-frequency daily inflation telemetry)', fontsize=6.2, ha='center', color='#134E4A', zorder=4)
ax.text(cx4 + col_w/2, col_y + 0.7, 'REST API & Automated Daily PDF Reports', fontsize=6.2, ha='center', color='#0F766E', fontweight='bold', zorder=4)


# ═══════════════════════════════════════════════════════════════════════
# CONNECTING FLOW ARROWS BETWEEN LAYERS
# ═══════════════════════════════════════════════════════════════════════
draw_arrow(ax, cx1 + col_w + 0.04, col_y + col_h/2, cx2 - 0.04, col_y + col_h/2, color='#0284C7', lw=2.0)
draw_arrow(ax, cx2 + col_w + 0.04, col_y + col_h/2, cx3 - 0.04, col_y + col_h/2, color='#4F46E5', lw=2.0)
draw_arrow(ax, cx3 + col_w + 0.04, col_y + col_h/2, cx4 - 0.04, col_y + col_h/2, color='#D97706', lw=2.0)


# ═══════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE & ORCHESTRATION BANNER (Bottom Row)
# ═══════════════════════════════════════════════════════════════════════
draw_box(ax, 0.8, 0.5, 18.5, 1.6, bg='#F8FAFC', border='#64748B', lw=1.4, zorder=2)
ax.text(1.1, 1.75, 'PLATFORM ORCHESTRATION & STORAGE BACKBONE', fontsize=8.2, fontweight='bold', color='#1E293B', zorder=4)

infra_badges = [
    ('Apache Airflow 2.10', 'cpi_master_dag • silver • gold', '#0284C7', '#E0F2FE'),
    ('PostgreSQL 16 Engine', 'cpi_db (Bronze/Silver/Gold/Ops)', '#2563EB', '#DBEAFE'),
    ('dbt Core Transformations', 'Seeds • Incremental delete+insert', '#EA580C', '#FFEDD5'),
    ('Gemini 2.5 3-Key Pool', '45 RPM • 4.5k/day • Auto-failover', '#7C3AED', '#EDE9FE'),
    ('Docker Compose', 'Containerized multi-service env', '#0D9488', '#CCFBF1'),
]

for bi, (btitle, bsub, bborder, bbg) in enumerate(infra_badges):
    bx = 1.05 + bi * 3.65
    draw_box(ax, bx, 0.65, 3.5, 0.9, bg=C_WHITE, border=bborder, lw=1.1, zorder=3)
    ax.text(bx + 1.75, 1.25, btitle, fontsize=7.2, fontweight='bold', ha='center', va='center', color=bborder, zorder=4)
    ax.text(bx + 1.75, 0.92, bsub, fontsize=5.8, ha='center', va='center', color='#475569', zorder=4)


# ═══════════════════════════════════════════════════════════════════════
# SAVE TO DISK
# ═══════════════════════════════════════════════════════════════════════
output_path = r'D:\CPI PIPELINE\docs\diagrams\cpi_pipeline_end_to_end.png'
plt.savefig(output_path, dpi=110, bbox_inches='tight', facecolor='#FFFFFF', edgecolor='none', pad_inches=0.3)
plt.close()
print(f"[SUCCESS] End-to-End Pipeline Architecture Diagram rendered to: {output_path}")
