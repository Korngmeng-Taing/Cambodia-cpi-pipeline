"""
Silver Layer Architecture Diagram — Clean, High-Level Minimalist Design
Pure White Background (#FFFFFF) • Clean Visual Flow • Modern Typography & Spacing
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# Canvas Setup with Pure White Background (Landscape 16:10 format)
fig, ax = plt.subplots(1, 1, figsize=(16, 9.6))
ax.set_xlim(0, 20)
ax.set_ylim(0, 12)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#FFFFFF')

# ── Color Palette (Modern, Clean, High Contrast) ──
C_WHITE = '#FFFFFF'
C_DARK = '#0F172A'
C_MUTED = '#64748B'

# High-Level Step Configs
STEPS = [
    {
        "num": "01",
        "title": "BRONZE INGESTION",
        "sub": "Raw Price Feeds",
        "desc": "20+ Retailer Web Scrapes\n& MEF Daily FX Rates",
        "border": "#0284C7",
        "bg": "#F0F9FF",
        "tag": "bronze.raw_prices",
        "tag_bg": "#E0F2FE",
        "tag_col": "#0369A1"
    },
    {
        "num": "02",
        "title": "ITEM MATCHING",
        "sub": "Canonical Resolution",
        "desc": "768-dim Vector Embeddings\nRapidFuzz + Spec Guards\nGemini AI Arbitration",
        "border": "#2563EB",
        "bg": "#EFF6FF",
        "tag": "silver.canonical_items",
        "tag_bg": "#DBEAFE",
        "tag_col": "#1D4ED8"
    },
    {
        "num": "03",
        "title": "DATA HYGIENE",
        "sub": "Standardization & FX",
        "desc": "USD to KHR MEF Conversion\nKhmer Text Normalization\nUnit Pricing (g, kg, ml, L)",
        "border": "#7C3AED",
        "bg": "#F5F3FF",
        "tag": "staging.int_prices_cleaned",
        "tag_bg": "#EDE9FE",
        "tag_col": "#6D28D9"
    },
    {
        "num": "04",
        "title": "COICOP CLASSIFIER",
        "sub": "12-Division Hierarchy",
        "desc": "Human Overrides & Store Locks\nVector Cosine Similarity\nGemini AI 3-Key Pool",
        "border": "#D97706",
        "bg": "#FFFBEB",
        "tag": "staging.int_coicop_classified",
        "tag_bg": "#FEF3C7",
        "tag_col": "#B45309"
    },
    {
        "num": "05",
        "title": "SILVER ASSEMBLY",
        "sub": "Unified Observations",
        "desc": "Clean Daily Store Quotes\nPositive Price Quality Gate\nHedonic Quality Adjustments",
        "border": "#16A34A",
        "bg": "#F0FDF4",
        "tag": "silver.clean_store_prices",
        "tag_bg": "#DCFCE7",
        "tag_col": "#15803D"
    }
]


def draw_box(ax, x, y, w, h, bg=C_WHITE, border='#CBD5E1', lw=1.5, zorder=2):
    box = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.04', facecolor=bg,
                         edgecolor=border, linewidth=lw, zorder=zorder)
    ax.add_patch(box)


def draw_arrow(ax, x1, y1, x2, y2, color='#64748B', lw=2.0, zorder=3):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                               connectionstyle='arc3,rad=0', mutation_scale=14), zorder=zorder)


# ═══════════════════════════════════════════════════════════════════════
# HEADER (Clean, Minimalist, White Background)
# ═══════════════════════════════════════════════════════════════════════
ax.text(10, 11.2, 'CAMBODIA DAILY CPI PIPELINE', fontsize=11, fontweight='bold',
        ha='center', va='center', color='#0F766E', zorder=5)
ax.text(10, 10.6, 'Silver Layer Architecture — High-Level Design',
        fontsize=22, fontweight='bold', ha='center', va='center', color='#0F172A', zorder=5)
ax.text(10, 10.1, 'From Raw Web Scrapes to Standardized, Conformed Daily Store-Level Price Facts',
        fontsize=10.5, ha='center', va='center', color='#64748B', zorder=5)

ax.plot([1.5, 18.5], [9.6, 9.6], color='#E2E8F0', linewidth=1.5, zorder=1)


# ═══════════════════════════════════════════════════════════════════════
# MAIN 5-STAGE PIPELINE FLOW (Horizontal Clean Cards)
# ═══════════════════════════════════════════════════════════════════════
card_w = 3.2
card_h = 5.3
y_card = 3.5
x_starts = [1.0, 4.8, 8.6, 12.4, 16.2]

for i, (cfg, x_pos) in enumerate(zip(STEPS, x_starts)):
    # Outer Card
    draw_box(ax, x_pos, y_card, card_w, card_h, bg=cfg["bg"], border=cfg["border"], lw=2.0, zorder=2)
    
    # Step Number Badge (Centered)
    draw_box(ax, x_pos + (card_w / 2) - 0.5, y_card + card_h - 0.65, 1.0, 0.45,
             bg=cfg["border"], border=cfg["border"], lw=1, zorder=3)
    ax.text(x_pos + (card_w / 2), y_card + card_h - 0.42, f"STEP {cfg['num']}", fontsize=8.0, fontweight='bold',
            ha='center', va='center', color=C_WHITE, zorder=4)
    
    # Stage Title (Centered)
    ax.text(x_pos + (card_w / 2), y_card + card_h - 1.05, cfg["title"], fontsize=9.0, fontweight='bold',
            ha='center', va='center', color=cfg["border"], zorder=4)
    
    # Subtitle (Centered)
    ax.text(x_pos + (card_w / 2), y_card + card_h - 1.45, cfg["sub"], fontsize=8.5, fontweight='bold',
            ha='center', va='center', color='#1E293B', zorder=4)
    
    # Divider inside card
    ax.plot([x_pos + 0.3, x_pos + card_w - 0.3], [y_card + card_h - 1.75, y_card + card_h - 1.75],
            color='#CBD5E1', linewidth=1, zorder=3)
    
    # Description Bullets
    ax.text(x_pos + (card_w / 2), y_card + card_h - 2.85, cfg["desc"], fontsize=8.2,
            ha='center', va='center', color='#334155', zorder=4, linespacing=1.6)
    
    # Bottom Table Tag Badge
    draw_box(ax, x_pos + 0.2, y_card + 0.3, card_w - 0.4, 0.60, bg=cfg["tag_bg"], border=cfg["border"], lw=1.2, zorder=3)
    ax.text(x_pos + (card_w / 2), y_card + 0.60, cfg["tag"], fontsize=7.2, fontweight='bold',
            ha='center', va='center', color=cfg["tag_col"], zorder=4)
    
    # Arrow to next card
    if i < len(STEPS) - 1:
        draw_arrow(ax, x_pos + card_w + 0.05, y_card + card_h / 2, x_starts[i+1] - 0.05, y_card + card_h / 2,
                   color='#64748B', lw=2.2)


# ═══════════════════════════════════════════════════════════════════════
# BOTTOM CONSUMER: GOLD STAR SCHEMA & MARTS
# ═══════════════════════════════════════════════════════════════════════
draw_arrow(ax, 17.8, y_card, 17.8, 2.05, color='#16A34A', lw=2.5)

draw_box(ax, 1.0, 0.7, 18.4, 1.35, bg='#FEFCE8', border='#D97706', lw=1.8, zorder=2)
ax.text(3.4, 1.38, 'GOLD LAYER CONSUMERS', fontsize=10.0, fontweight='bold',
        ha='center', va='center', color='#B45309', zorder=4)

gold_tables = [
    ('gold.dim_items', 'Canonical Master'),
    ('gold.dim_stores', 'Store Directory'),
    ('gold.fct_daily_prices', 'Conformed Prices'),
    ('gold.fct_cpi_daily', 'Jevons / CPI Index'),
]

for gi, (gtbl, gdesc) in enumerate(gold_tables):
    gx = 6.2 + gi * 3.15
    draw_box(ax, gx, 0.82, 2.9, 1.0, bg=C_WHITE, border='#F59E0B', lw=1.2, zorder=3)
    ax.text(gx + 1.45, 1.45, gtbl, fontsize=7.8, fontweight='bold', ha='center', va='center', color='#92400E', zorder=4)
    ax.text(gx + 1.45, 1.10, gdesc, fontsize=6.8, ha='center', va='center', color='#78350F', zorder=4)


# ═══════════════════════════════════════════════════════════════════════
# SAVE TO DISK
# ═══════════════════════════════════════════════════════════════════════
output_path = r'D:\CPI PIPELINE\docs\diagrams\silver_layer_simplified.png'
plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='#FFFFFF', edgecolor='none', pad_inches=0.3)
plt.close()
print(f"[SUCCESS] Clean High-Level White Background Diagram rendered to: {output_path}")
