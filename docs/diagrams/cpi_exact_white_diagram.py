"""
Cambodia National Consumer Price Index (CPI) Medallion Pipeline — White Theme Architecture Diagram
Faithfully matches the layout, iconography, components, and structure of cpi_end_to_end_architecture_diagram.jpg
Rendered on a crisp, professional Pure White Background (#FFFFFF).
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Ellipse

# ═══════════════════════════════════════════════════════════════════════
# CANVAS SETUP (16:9 High-Res Landscape, Pure White Background)
# ═══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(1, 1, figsize=(20, 11.25))
ax.set_xlim(0, 24)
ax.set_ylim(0, 13.5)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#FFFFFF')

# ── Color Palette (Crisp White Theme Adaptation) ──
C_WHITE = '#FFFFFF'
C_DARK = '#0F172A'
C_SLATE = '#334155'
C_MUTED = '#64748B'
C_LINE = '#94A3B8'

# Column Colors
COL1_BORDER = '#0284C7'   # Sky Blue (Bronze/Sources)
COL1_BG = '#F8FAFC'
COL1_HDR = '#0369A1'

COL2_BORDER = '#4F46E5'   # Indigo (Silver)
COL2_BG = '#F8FAFC'
COL2_HDR = '#3730A3'

COL3_BORDER = '#D97706'   # Amber/Gold (Gold)
COL3_BG = '#F8FAFC'
COL3_HDR = '#92400E'

COL4_BORDER = '#0D9488'   # Teal (Serving)
COL4_BG = '#F8FAFC'
COL4_HDR = '#115E59'

COL_FLOW = '#0284C7'      # Cyan/Blue Flow Lines


def draw_box(ax, x, y, w, h, bg=C_WHITE, border='#CBD5E1', lw=1.5, zorder=2, pad=0.03):
    box = FancyBboxPatch((x, y), w, h, boxstyle=f'round,pad={pad}', facecolor=bg,
                         edgecolor=border, linewidth=lw, zorder=zorder)
    ax.add_patch(box)


def draw_db_icon(ax, x, y, w, h, title='', subtitle='', bg='#EFF6FF', border='#2563EB', title_col='#1E3A8A', zorder=3):
    """Draws a cylinder database shape."""
    # Body
    rect = FancyBboxPatch((x, y), w, h - 0.15, boxstyle='round,pad=0.02',
                          facecolor=bg, edgecolor=border, linewidth=1.4, zorder=zorder)
    ax.add_patch(rect)
    # Top ellipse
    ell_top = Ellipse((x + w/2, y + h - 0.08), w, 0.22, facecolor=bg,
                      edgecolor=border, linewidth=1.4, zorder=zorder+1)
    ax.add_patch(ell_top)
    # Bottom ellipse
    ell_bot = Ellipse((x + w/2, y + 0.08), w, 0.22, facecolor=bg,
                      edgecolor=border, linewidth=1.4, zorder=zorder)
    ax.add_patch(ell_bot)
    
    if subtitle:
        ax.text(x + w/2, y + (h/2) + 0.10, title, fontsize=7.8, fontweight='bold',
                ha='center', va='center', color=title_col, zorder=zorder+2)
        ax.text(x + w/2, y + (h/2) - 0.18, subtitle, fontsize=6.2, fontweight='normal',
                ha='center', va='center', color=C_MUTED, zorder=zorder+2)
    else:
        ax.text(x + w/2, y + h/2, title, fontsize=8.0, fontweight='bold',
                ha='center', va='center', color=title_col, zorder=zorder+2)


def draw_arrow_flow(ax, x1, y1, x2, y2, color=COL_FLOW, lw=2.0, zorder=5):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                               connectionstyle='arc3,rad=0', mutation_scale=13), zorder=zorder)


def draw_curved_pipe(ax, x1, y1, x2, y2, color=COL_FLOW, lw=1.8, rad=0.2, zorder=5):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                               connectionstyle=f'arc3,rad={rad}', mutation_scale=12), zorder=zorder)


# ═══════════════════════════════════════════════════════════════════════
# TITLE (Exact match with reference image)
# ═══════════════════════════════════════════════════════════════════════
ax.text(12, 12.85, 'Cambodia National Consumer Price Index (CPI) Medallion Pipeline',
        fontsize=20, fontweight='bold', ha='center', va='center', color=C_DARK, zorder=6)


# ═══════════════════════════════════════════════════════════════════════
# 4 MAIN COLUMNS SETUP
# ═══════════════════════════════════════════════════════════════════════
col_y = 2.0
col_h = 10.2

# ─────────────────────────────────────────────────────────────────────
# 1. SOURCES & BRONZE LAYER (Left Column)
# ─────────────────────────────────────────────────────────────────────
c1_x, c1_w = 0.5, 6.2
draw_box(ax, c1_x, col_y, c1_w, col_h, bg='#F0F9FF', border=COL1_BORDER, lw=1.8, zorder=2)
ax.text(c1_x + c1_w/2, col_y + col_h - 0.45, 'Sources & Bronze Layer',
        fontsize=11.5, fontweight='bold', ha='center', va='center', color=COL1_HDR, zorder=4)

# Sub-container 1.1: 20 Web Scrapers (Left inner box)
s_box_x, s_box_w = c1_x + 0.25, 2.7
s_box_y, s_box_h = col_y + 0.4, 9.0
draw_box(ax, s_box_x, s_box_y, s_box_w, s_box_h, bg=C_WHITE, border='#BAE6FD', lw=1.2, zorder=3)
ax.text(s_box_x + s_box_w/2, s_box_y + s_box_h - 0.45, '20 Web scrapers',
        fontsize=9.0, fontweight='bold', ha='center', va='center', color='#0369A1', zorder=5)

scrapers_list = [
    ('Supermarkets', '[Web]', '#0284C7'),
    ('Electronics', '[Web]', '#0284C7'),
    ('Pharmacies', '[Rx]', '#0D9488'),
    ('Telecom', '[Web]', '#0284C7'),
    ('Transport', '[Bus]', '#2563EB'),
    ('Housing', '[Prop]', '#EA580C'),
    ('MEF FX Rates', '[Bank]', '#4F46E5')
]

for si, (sname, sicon, scol) in enumerate(scrapers_list):
    sy = s_box_y + s_box_h - 1.25 - (si * 1.05)
    # Scraper Pill
    draw_box(ax, s_box_x + 0.15, sy, s_box_w - 0.3, 0.75, bg='#F8FAFC', border='#CBD5E1', lw=1.0, zorder=4)
    ax.text(s_box_x + 0.35, sy + 0.38, sname, fontsize=7.5, fontweight='bold', ha='left', va='center', color='#1E293B', zorder=5)
    # Icon pill
    draw_box(ax, s_box_x + s_box_w - 0.85, sy + 0.15, 0.55, 0.45, bg=C_WHITE, border=scol, lw=0.9, zorder=5)
    ax.text(s_box_x + s_box_w - 0.57, sy + 0.38, sicon, fontsize=5.8, fontweight='bold', ha='center', va='center', color=scol, zorder=6)

# Sub-container 1.2: raw PostgreSQL Bronze tables (Right inner box)
b_box_x, b_box_w = c1_x + 3.3, 2.65
b_box_y, b_box_h = col_y + 1.8, 6.2
draw_box(ax, b_box_x, b_box_y, b_box_w, b_box_h, bg='#FFFBEB', border='#F59E0B', lw=1.3, zorder=3)

# Postgres Header
ax.text(b_box_x + b_box_w/2, b_box_y + b_box_h - 0.45, '[PGSQL] PostgreSQL', fontsize=8.0, fontweight='bold', ha='center', va='center', color='#92400E', zorder=5)
ax.text(b_box_x + b_box_w/2, b_box_y + b_box_h - 0.80, 'Bronze tables', fontsize=8.0, fontweight='bold', ha='center', va='center', color='#92400E', zorder=5)

# 2 Cylinder tables inside Bronze
draw_db_icon(ax, b_box_x + 0.25, b_box_y + 2.8, b_box_w - 0.5, 1.6, 'raw_prices', 'Raw JSON observations', bg=C_WHITE, border='#D97706', title_col='#92400E', zorder=4)
draw_db_icon(ax, b_box_x + 0.25, b_box_y + 0.6, b_box_w - 0.5, 1.6, 'raw_scrapes', 'Batch audit logs', bg=C_WHITE, border='#D97706', title_col='#92400E', zorder=4)

# Converging connector lines from scrapers to bronze DB
for si in range(len(scrapers_list)):
    sy = s_box_y + s_box_h - 1.25 - (si * 1.05) + 0.38
    draw_arrow_flow(ax, s_box_x + s_box_w, sy, b_box_x, b_box_y + 3.6, color='#0284C7', lw=1.2)


# ─────────────────────────────────────────────────────────────────────
# 2. SILVER TRANSFORMATION LAYER (Middle-Left Column)
# ─────────────────────────────────────────────────────────────────────
c2_x, c2_w = 7.1, 6.8
draw_box(ax, c2_x, col_y, c2_w, col_h, bg='#EEF2FF', border=COL2_BORDER, lw=1.8, zorder=2)
ax.text(c2_x + c2_w/2, col_y + col_h - 0.45, 'Silver Transformation Layer',
        fontsize=11.5, fontweight='bold', ha='center', va='center', color=COL2_HDR, zorder=4)

# Connector from Bronze DB to Silver
draw_arrow_flow(ax, b_box_x + b_box_w, b_box_y + 3.6, c2_x, col_y + col_h/2, color='#4F46E5', lw=2.2)

# 4 Stacked Horizontal Cards in Silver Layer
silver_cards = [
    {
        "title": "Intermediate price cleaning",
        "bullets": ["• USD to KHR conversion (MEF daily rate)", "• Discount clamping to [0%, 95%]", "• Unit normalization (g, kg, ml, L)"],
        "icon_left": "[DB]", "icon_right": "[AI Engine]"
    },
    {
        "title": "Entity deduplication engine",
        "bullets": ["• 768-dim Vector Embeddings + RapidFuzz", "• Deterministic Hardware Spec Guards", "• AI Auto-Reviewer (silver.needs_review)"],
        "icon_left": "[VEC]", "icon_right": "[AI Engine]"
    },
    {
        "title": "AI-First COICOP Classification Ladder",
        "bullets": ["• Tier 1: Authority Human Overrides", "• Tier 2: 15 Pure Store Domain Locks", "• Tier 3 & 4: 12-Division Vector & Gemini AI Cache"],
        "icon_left": "[CLS]", "icon_right": "[AI Engine]"
    },
    {
        "title": "Multi-attribute Hedonic Quality Adjustment",
        "bullets": [],
        "tags": ["RAM", "Storage", "Screen", "Camera", "5G"],
        "icon_left": "[HED]", "icon_right": None
    }
]

sc_y_starts = [col_y + 7.0, col_y + 4.8, col_y + 2.4, col_y + 0.35]
sc_heights = [2.05, 2.05, 2.25, 1.85]

for ci, (sc, sc_y, sc_h) in enumerate(zip(silver_cards, sc_y_starts, sc_heights)):
    draw_box(ax, c2_x + 0.3, sc_y, c2_w - 0.6, sc_h, bg=C_WHITE, border='#C7D2FE', lw=1.3, zorder=3)
    
    # Left Icon Badge
    draw_box(ax, c2_x + 0.5, sc_y + sc_h - 0.70, 0.7, 0.5, bg='#EEF2FF', border='#4F46E5', lw=0.9, zorder=4)
    ax.text(c2_x + 0.85, sc_y + sc_h - 0.45, sc["icon_left"], fontsize=6.8, fontweight='bold', ha='center', va='center', color='#4F46E5', zorder=5)
    
    # Right AI Icon Badge
    if sc["icon_right"]:
        draw_box(ax, c2_x + c2_w - 1.55, sc_y + sc_h - 0.70, 1.15, 0.5, bg='#FAF5FF', border='#9333EA', lw=0.9, zorder=4)
        ax.text(c2_x + c2_w - 0.97, sc_y + sc_h - 0.45, sc["icon_right"], fontsize=6.0, fontweight='bold', ha='center', va='center', color='#7E22CE', zorder=5)
    
    # Title
    ax.text(c2_x + 1.35, sc_y + sc_h - 0.45, sc["title"], fontsize=8.0, fontweight='bold', ha='left', va='center', color=C_DARK, zorder=5)
    
    # Bullets
    for bi, btext in enumerate(sc["bullets"]):
        ax.text(c2_x + 1.35, sc_y + sc_h - 0.82 - (bi * 0.36), btext, fontsize=6.5, ha='left', va='center', color=C_SLATE, zorder=5)
    
    # Tag Pills for Hedonic card
    if "tags" in sc:
        ax.text(c2_x + 1.35, sc_y + sc_h - 0.80, "Semi-log OLS Tech Spec Regression Engine (Div 08/09):", fontsize=6.5, ha='left', va='center', color=C_MUTED, zorder=5)
        for ti, tag in enumerate(sc["tags"]):
            tx = c2_x + 1.35 + ti * 0.95
            draw_box(ax, tx, sc_y + 0.25, 0.82, 0.42, bg='#F1F5F9', border='#64748B', lw=0.8, zorder=4)
            ax.text(tx + 0.41, sc_y + 0.46, tag, fontsize=6.5, fontweight='bold', ha='center', va='center', color='#334155', zorder=5)


# ─────────────────────────────────────────────────────────────────────
# 3. GOLD STAR SCHEMA LAYER (Middle-Right Column)
# ─────────────────────────────────────────────────────────────────────
c3_x, c3_w = 14.3, 4.8
draw_box(ax, c3_x, col_y, c3_w, col_h, bg='#FFFBEB', border=COL3_BORDER, lw=1.8, zorder=2)
ax.text(c3_x + c3_w/2, col_y + col_h - 0.45, 'Gold Star Schema Layer',
        fontsize=11.5, fontweight='bold', ha='center', va='center', color=COL3_HDR, zorder=4)

ax.text(c3_x + c3_w/2, col_y + col_h - 0.95, 'Dimensional models\nKimball Star Schema',
        fontsize=7.8, fontweight='bold', ha='center', va='center', color='#B45309', zorder=4)

# Connector from Silver to Gold
draw_arrow_flow(ax, c2_x + c2_w, col_y + 5.2, c3_x, col_y + 5.2, color='#D97706', lw=2.2)

# Top 2 Dimension DBs
draw_db_icon(ax, c3_x + 0.35, col_y + 6.6, 1.9, 1.8, 'dim_items', 'Canonical UUID PK', bg=C_WHITE, border='#0284C7', title_col='#0369A1', zorder=3)
draw_db_icon(ax, c3_x + 2.55, col_y + 6.6, 1.9, 1.8, 'dim_stores', 'Store Directory', bg=C_WHITE, border='#4F46E5', title_col='#3730A3', zorder=3)

# Arrows from Dimensions to Fact Table
draw_arrow_flow(ax, c3_x + 1.30, col_y + 6.6, c3_x + 2.0, col_y + 5.6, color='#64748B', lw=1.4)
draw_arrow_flow(ax, c3_x + 3.50, col_y + 6.6, c3_x + 2.8, col_y + 5.6, color='#64748B', lw=1.4)

# Central Fact Table
draw_db_icon(ax, c3_x + 0.9, col_y + 3.7, 3.0, 1.9, 'fct_daily_prices', 'Conformed Daily Fact Grain\n(date, store, item_id)', bg=C_WHITE, border='#0D9488', title_col='#0F766E', zorder=3)

# Arrow from Fact to Aggregations
draw_arrow_flow(ax, c3_x + c3_w/2, col_y + 3.7, c3_x + c3_w/2, col_y + 2.6, color='#D97706', lw=1.8)

# Bottom Aggregations Card
draw_box(ax, c3_x + 0.4, col_y + 0.4, c3_w - 0.8, 2.0, bg=C_WHITE, border='#F59E0B', lw=1.2, zorder=3)
ax.text(c3_x + c3_w/2, col_y + 1.85, 'Aggregations', fontsize=8.5, fontweight='bold', ha='center', va='center', color='#92400E', zorder=5)
ax.text(c3_x + c3_w/2, col_y + 1.45, '12 COICOP divisions', fontsize=7.8, fontweight='bold', ha='center', va='center', color='#B45309', zorder=5)
ax.text(c3_x + c3_w/2, col_y + 0.95, '• Jevons Micro-Index (Geometric)\n• 12-Division Weighted Laspeyres', fontsize=6.5, ha='center', va='center', color=C_SLATE, zorder=5)


# ─────────────────────────────────────────────────────────────────────
# 4. SERVING & BI LAYER (Right Column)
# ─────────────────────────────────────────────────────────────────────
c4_x, c4_w = 19.5, 4.0
draw_box(ax, c4_x, col_y, c4_w, col_h, bg='#F0FDFA', border=COL4_BORDER, lw=1.8, zorder=2)
ax.text(c4_x + c4_w/2, col_y + col_h - 0.45, 'Serving & BI Layer',
        fontsize=11.5, fontweight='bold', ha='center', va='center', color=COL4_HDR, zorder=4)

# Connector from Gold to Serving
draw_arrow_flow(ax, c3_x + c3_w, col_y + 5.2, c4_x, col_y + 7.8, color='#0D9488', lw=1.8)
draw_arrow_flow(ax, c3_x + c3_w, col_y + 5.2, c4_x, col_y + 4.8, color='#0D9488', lw=1.8)
draw_arrow_flow(ax, c3_x + c3_w, col_y + 5.2, c4_x, col_y + 1.8, color='#0D9488', lw=1.8)

# 3 Stacked Serving Cards
bi_cards = [
    {
        "icon": "[DASH]",
        "text": "Real-time Metabase\nmonitoring dashboards",
        "y": col_y + 6.6, "h": 2.5
    },
    {
        "icon": "[GRID]",
        "text": "20-source health\nmatrix & SLA feeds",
        "y": col_y + 3.6, "h": 2.5
    },
    {
        "icon": "[CHART]",
        "text": "Power BI macro\ninflation analytics\n& ML Nowcasts",
        "y": col_y + 0.6, "h": 2.5
    }
]

for bc in bi_cards:
    draw_box(ax, c4_x + 0.3, bc["y"], c4_w - 0.6, bc["h"], bg=C_WHITE, border='#99F6E4', lw=1.3, zorder=3)
    # Icon box
    draw_box(ax, c4_x + c4_w/2 - 0.6, bc["y"] + bc["h"] - 0.9, 1.2, 0.6, bg='#F0FDFA', border='#0D9488', lw=0.9, zorder=4)
    ax.text(c4_x + c4_w/2, bc["y"] + bc["h"] - 0.6, bc["icon"], fontsize=7.2, fontweight='bold', ha='center', va='center', color='#0F766E', zorder=5)
    # Text
    ax.text(c4_x + c4_w/2, bc["y"] + 0.75, bc["text"], fontsize=7.5, fontweight='bold', ha='center', va='center', color=C_DARK, zorder=5)


# ═══════════════════════════════════════════════════════════════════════
# BOTTOM BAR: AIRFLOW MASTER ORCHESTRATION (Exact match with reference)
# ═══════════════════════════════════════════════════════════════════════
bot_x, bot_y, bot_w, bot_h = 0.5, 0.4, 23.0, 1.3
draw_box(ax, bot_x, bot_y, bot_w, bot_h, bg='#F8FAFC', border='#475569', lw=1.5, zorder=2)

# Airflow Icon & Title
draw_box(ax, bot_x + 0.3, bot_y + 0.25, 0.8, 0.8, bg='#E0F2FE', border='#0284C7', lw=1.0, zorder=3)
ax.text(bot_x + 0.7, bot_y + 0.65, '[DAG]', fontsize=8.5, fontweight='bold', ha='center', va='center', color='#0284C7', zorder=4)

ax.text(bot_x + 1.3, bot_y + 0.80, 'Bottom Bar: Airflow Orchestration', fontsize=9.0, fontweight='bold', ha='left', va='center', color=C_DARK, zorder=4)
ax.text(bot_x + 1.3, bot_y + 0.45, 'master orchestration workflow', fontsize=7.5, fontweight='normal', ha='left', va='center', color=C_MUTED, zorder=4)

# 3 DAG Workflow Pills
dag_pills = ['cpi_master_dag', 'silver_dag', 'gold_dag']
dag_xs = [bot_x + 9.5, bot_x + 14.5, bot_x + 19.5]

for di, (dname, dx) in enumerate(zip(dag_pills, dag_xs)):
    draw_box(ax, dx, bot_y + 0.3, 3.6, 0.7, bg=C_WHITE, border='#0284C7' if di==0 else ('#4F46E5' if di==1 else '#D97706'), lw=1.3, zorder=3)
    ax.text(dx + 1.8, bot_y + 0.65, dname, fontsize=8.0, fontweight='bold', ha='center', va='center',
            color='#0369A1' if di==0 else ('#3730A3' if di==1 else '#92400E'), zorder=4)
    
    if di < len(dag_pills) - 1:
        draw_arrow_flow(ax, dx + 3.65, bot_y + 0.65, dag_xs[di+1] - 0.05, bot_y + 0.65, color='#64748B', lw=1.8)


# ═══════════════════════════════════════════════════════════════════════
# SAVE TO DISK
# ═══════════════════════════════════════════════════════════════════════
output_path = r'D:\CPI PIPELINE\docs\diagrams\cpi_end_to_end_white.png'
plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='#FFFFFF', edgecolor='none', pad_inches=0.3)
plt.close()
print(f"[SUCCESS] Exact Format White Background Diagram rendered to: {output_path}")
