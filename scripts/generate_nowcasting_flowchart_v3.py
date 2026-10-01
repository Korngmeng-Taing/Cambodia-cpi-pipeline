"""
scripts/generate_nowcasting_flowchart_v3.py
───────────────────────────────────────────
Generates a modern, intuitive, high-resolution flowchart for the 
Cambodia CPI Two-Tier Inflation Nowcasting Engine.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def create_flowchart(output_path="thesis/images/nowcasting_flowchart.png"):
    fig, ax = plt.subplots(figsize=(12, 7.5), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')
    fig.patch.set_facecolor('#FFFFFF')

    # Palette
    C_NAVY    = '#0C2C62'  # #0C2C62 Primary Dark
    C_TEAL    = '#0F766E'  # #0F766E Realized / Truth
    C_BLUE    = '#1D4ED8'  # #1D4ED8 Machine Learning / Ridge
    C_PURPLE  = '#4338CA'  # #4338CA Blending
    C_GREEN   = '#047857'  # #047857 Final Output
    C_DARK    = '#1E293B'  # Slate 800
    C_MUTED   = '#475569'  # Slate 600
    C_LINE    = '#64748B'  # Arrows / connecting lines

    # Background banner at top
    banner = patches.FancyBboxPatch(
        (3, 91.5), 94, 7.5,
        boxstyle='round,pad=0.2,rounding_size=1.5',
        facecolor='#F1F5F9', edgecolor='#CBD5E1', lw=1.2
    )
    ax.add_patch(banner)
    ax.text(50, 95.8, "TWO-TIER INFLATION NOWCASTING ENGINE", 
            color=C_NAVY, weight='bold', fontsize=13, ha='center', va='center')
    ax.text(50, 93.0, "Bridging the Official Statistical Lag with Daily Scraped Microdata & RidgeCV Bayesian Shrinkage", 
            color=C_MUTED, fontsize=8.5, ha='center', va='center', style='italic')

    # Card drawing helper
    def draw_card(x, y, w, h, title, subtitle, bullets, hdr_color=C_NAVY, bg_color='#F8FAFC', border_color='#CBD5E1'):
        hdr_h = 7.0
        # Header tab
        hdr = patches.FancyBboxPatch(
            (x, y + h - hdr_h), w, hdr_h,
            boxstyle='round,pad=0.2,rounding_size=1.5',
            facecolor=hdr_color, edgecolor=hdr_color, lw=1
        )
        ax.add_patch(hdr)
        ax.text(x + w/2, y + h - 2.8, title, color='#FFFFFF', weight='bold', fontsize=9.2, ha='center', va='center')
        if subtitle:
            ax.text(x + w/2, y + h - 5.2, subtitle, color='#E2E8F0', fontsize=7.2, ha='center', va='center')

        # Card body
        body_h = h - hdr_h + 1.2
        body = patches.FancyBboxPatch(
            (x, y), w, body_h,
            boxstyle='round,pad=0.2,rounding_size=1.5',
            facecolor=bg_color, edgecolor=border_color, lw=1.2
        )
        ax.add_patch(body)

        # Content bullets
        cur_y = y + h - hdr_h - 2.2
        for b_title, b_desc in bullets:
            ax.text(x + 2.0, cur_y, f"> {b_title}", color=C_DARK, weight='bold', fontsize=7.8, va='top')
            offset = len(b_title) * 0.52 + 3.0
            ax.text(x + 2.0 + offset, cur_y, b_desc, color=C_MUTED, fontsize=7.6, va='top')
            cur_y -= 3.8

    # ── STAGE 1: Microdata & Elementary Jevons (Top) ──────────────────────────
    draw_card(
        x=10, y=74, w=80, h=15.5,
        title="STAGE 1: DAILY MICRODATA INGESTION & JEVONS AGGREGATION",
        subtitle="11 Daily Retail Stores  |  12 Official UN COICOP Baskets  |  Equal Store Voting (1 Store = 1 Vote)",
        bullets=[
            ("Daily Scraped Microdata: ", "Automated daily collection from AEON, DeliShop, GrabMart, L192, Khmer24, Tela Khmer, MEF FX."),
            ("Store-Balanced Jevons: ", "Calculates geometric mean per store: ln(I) = (1/n) * sum(ln(P_t) - ln(P_0)) to eliminate formula drift."),
            ("Elementary Aggregates: ", "Equal store voting prevents large catalogs from overpowering small shops across product categories.")
        ],
        hdr_color=C_NAVY, bg_color='#F8FAFC', border_color='#94A3B8'
    )

    # Down arrow to Timeline Split
    ax.annotate('', xy=(50, 69.5), xytext=(50, 74), arrowprops=dict(arrowstyle='->', lw=2.0, color=C_LINE))

    # Timeline Divider Banner
    tbox = patches.FancyBboxPatch(
        (20, 65.5), 60, 4.0,
        boxstyle='round,pad=0.2,rounding_size=1.0',
        facecolor='#E2E8F0', edgecolor='#94A3B8', lw=1
    )
    ax.add_patch(tbox)
    ax.text(50, 67.5, "CURRENT MONTH SPLIT: Day 1 to Today (Elapsed d) vs. Tomorrow to Month-End (Remaining T-d)",
            color=C_DARK, weight='bold', fontsize=7.8, ha='center', va='center')

    # Branching arrows down to Tier 1 and Tier 2
    ax.annotate('', xy=(27, 60.5), xytext=(35, 65.5), arrowprops=dict(arrowstyle='->', lw=2.0, color=C_LINE))
    ax.annotate('', xy=(73, 60.5), xytext=(65, 65.5), arrowprops=dict(arrowstyle='->', lw=2.0, color=C_LINE))

    # ── STAGE 2A: Tier 1 - Realized MTD (Left) ────────────────────────────────
    draw_card(
        x=5, y=36.5, w=43, h=24.0,
        title="TIER 1: REALIZED ELAPSED DAYS (1 to d)",
        subtitle="100% Axiomatic Scraped Reality  |  Zero Model Error",
        bullets=[
            ("Observed Window: ", "Covers elapsed days (Day 1 up to today d) of ongoing month."),
            ("Arithmetic Mean: ", "Realized daily average: Realized_Mean = (1/d) * sum(I_t)."),
            ("Ground Truth: ", "Built from verified retail shelf prices collected each morning."),
            ("Lag Killer: ", "Eliminates the official 25-45 day statistical reporting lag.")
        ],
        hdr_color=C_TEAL, bg_color='#F0FDFA', border_color='#5EEAD4'
    )

    # ── STAGE 2B: Tier 2 - Forward RidgeCV (Right) ────────────────────────────
    draw_card(
        x=52, y=36.5, w=43, h=24.0,
        title="TIER 2: FORWARD PROJECTION (d+1 to T)",
        subtitle="RidgeCV Regularization  |  Bayesian Prior Shrinkage",
        bullets=[
            ("Unobserved Window: ", "Covers remaining future days (d+1 to month-end T)."),
            ("L2 Ridge Shrinkage: ", "Prevents multicollinearity from blowing up regression weights."),
            ("Leading Signals: ", "Fuel logistics pass-through, USD/KHR exchange rate momentum."),
            ("Khmer Calendar: ", "Exponential decay adjustments for holidays (Pchum Ben, etc.).")
        ],
        hdr_color=C_BLUE, bg_color='#EFF6FF', border_color='#93C5FD'
    )

    # Arrows converging to Stage 3 (Blending)
    ax.annotate('', xy=(42, 32.5), xytext=(27, 36.5), arrowprops=dict(arrowstyle='->', lw=2.0, color=C_LINE))
    ax.annotate('', xy=(58, 32.5), xytext=(73, 36.5), arrowprops=dict(arrowstyle='->', lw=2.0, color=C_LINE))

    # ── STAGE 3: Time-Weighted Horizon Blending (Middle) ──────────────────────
    draw_card(
        x=10, y=18.5, w=80, h=14.0,
        title="STAGE 3: TIME-WEIGHTED HORIZON BLENDING ENGINE",
        subtitle="Nowcast(d) = ( d / T ) * Realized_Mean + ( (T - d) / T ) * Projected_Mean",
        bullets=[
            ("Dynamic Horizon Blending: ", "Day 1 is 3% realized + 97% projected; Day 15 is 50/50; Day 30 is 100% ground truth."),
            ("Decaying Uncertainty Envelope: ", "Error bounds shrink monotonically: Uncertainty = sqrt((T - d) / T), dropping to zero at month-end.")
        ],
        hdr_color=C_PURPLE, bg_color='#FAF5FF', border_color='#D8B4FE'
    )

    # Down arrow to Stage 4
    ax.annotate('', xy=(50, 14.5), xytext=(50, 18.5), arrowprops=dict(arrowstyle='->', lw=2.0, color=C_LINE))

    # ── STAGE 4: Laspeyres Synthesis & Policy Decision Support (Bottom) ───────
    draw_card(
        x=5, y=1.0, w=90, h=13.5,
        title="STAGE 4: CSES 2020 LASPEYRES SYNTHESIS & EARLY POLICY INTELLIGENCE",
        subtitle="Headline CPI  |  Refined Core CPI  |  Published 2 to 4 Weeks Ahead of Official NIS Releases",
        bullets=[
            ("Official CSES Weights: ", "Food (44.8%), Housing & Utilities (17.1%), Transport & Fuel (12.2%), All Other 9 Divisions (26.0%)."),
            ("Dual Core Metrics: ", "Headline CPI tracks complete consumer basket; Core CPI removes volatile food & fuel for structural trend."),
            ("Policy Early Warning: ", "Re-anchored to NIS 2006=100 base (multiplier 2.19007), giving MEF daily inflation intelligence in real time.")
        ],
        hdr_color=C_GREEN, bg_color='#F0FDF4', border_color='#86EFAC'
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Flowchart successfully generated at: {output_path}")

if __name__ == "__main__":
    create_flowchart("thesis/images/nowcasting_flowchart.png")
