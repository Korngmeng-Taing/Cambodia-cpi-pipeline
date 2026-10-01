"""
scripts/generate_clean_nowcasting_flowchart.py
──────────────────────────────────────────────
Generates a pristine, high-resolution, modern flowchart for the 
Two-Tier Cambodia Inflation Nowcasting Engine.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generate_flowchart(output_path="thesis/images/nowcasting_flowchart.png"):
    fig, ax = plt.subplots(figsize=(11.5, 7.2), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')
    fig.patch.set_facecolor('#FFFFFF')

    # Color Palette
    DARK_NAVY  = '#0C2C62'  # Headers / Core
    TEAL       = '#0D9488'  # Realized / Ground Truth
    ROYAL_BLUE = '#2563EB'  # Projections / Machine Learning
    SLATE_DARK = '#1E293B'  # Aggregation / Synthesis
    LIGHT_BG   = '#F8FAFC'  # Box backgrounds
    CARD_EDGE  = '#CBD5E1'  # Border
    TEXT_MAIN  = '#0F172A'  # Main text
    TEXT_MUTED = '#475569'  # Secondary text

    def draw_card(x, y, w, h, title, subtitle, bullets, title_bg=DARK_NAVY, body_bg=LIGHT_BG, edge_color=CARD_EDGE):
        # Header box
        hdr_h = 8.5
        hdr = patches.FancyBboxPatch(
            (x, y + h - hdr_h), w, hdr_h,
            boxstyle='round,pad=0.2,rounding_size=2.0',
            facecolor=title_bg, edgecolor=title_bg, lw=1
        )
        ax.add_patch(hdr)
        ax.text(x + w/2, y + h - 3.2, title, color='#FFFFFF', weight='bold', fontsize=9.5, ha='center', va='center')
        if subtitle:
            ax.text(x + w/2, y + h - 6.5, subtitle, color='#E2E8F0', fontsize=7.2, ha='center', va='center', style='italic')

        # Body box
        body_h = h - hdr_h + 1.5
        body = patches.FancyBboxPatch(
            (x, y), w, body_h,
            boxstyle='round,pad=0.2,rounding_size=2.0',
            facecolor=body_bg, edgecolor=edge_color, lw=1.2
        )
        ax.add_patch(body)

        # Bullets
        cur_y = y + h - hdr_h - 2.5
        for b_bold, b_text in bullets:
            t = ax.text(x + 2.2, cur_y, f"- {b_bold}", color=TEXT_MAIN, weight='bold', fontsize=8.0, va='top')
            offset = len(b_bold) * 0.58 + 2.8
            ax.text(x + 2.2 + offset, cur_y, b_text, color=TEXT_MUTED, fontsize=7.8, va='top')
            cur_y -= 4.2

    # 1. Top Card: Daily Microdata & Gold Fact Compilation
    draw_card(
        x=16, y=81, w=68, h=16,
        title="1. DAILY WEB MICRODATA & GOLD FACT COMPILATION",
        subtitle="11 Daily Retail Stores  |  12 Official COICOP Divisions  |  Equal Store Voting (1 Store = 1 Vote)",
        bullets=[
            ("Input Microdata: ", "Automated scraping across supermarkets, fuel, housing, telco, transit, and MEF FX rates"),
            ("Axiomatic Aggregation: ", "Computes daily store-level Jevons index using numerical log-prices to eliminate formula drift")
        ],
        title_bg=DARK_NAVY, body_bg='#F1F5F9', edge_color='#94A3B8'
    )

    # Arrows from Top to Two Tiers
    ax.annotate('', xy=(28, 77), xytext=(38, 81), arrowprops=dict(arrowstyle='->', lw=2.0, color='#64748B'))
    ax.annotate('', xy=(72, 77), xytext=(62, 81), arrowprops=dict(arrowstyle='->', lw=2.0, color='#64748B'))

    # 2. Tier 1: Realized MTD Observed Days (Left)
    draw_card(
        x=4, y=47, w=44, h=28,
        title="TIER 1: REALIZED ELAPSED DAYS (1 to d)",
        subtitle="100% Axiomatic Scraped Reality  |  Zero Econometric Error",
        bullets=[
            ("Elapsed Window: ", "Observed days (Day 1 up to today d) of the ongoing month"),
            ("Daily Realized CPI: ", "Arithmetic mean of verified daily Jevons aggregates"),
            ("Axiomatic Ground Truth: ", "Reflects actual price quotes collected from retail shelves"),
            ("Lag Elimination: ", "Removes the official 25-to-45 day statistical reporting delay")
        ],
        title_bg=TEAL, body_bg='#F0FDFA', edge_color='#5EEAD4'
    )

    # 3. Tier 2: Forward Econometric Projection (Right)
    draw_card(
        x=52, y=47, w=44, h=28,
        title="TIER 2: FORWARD PROJECTION (d+1 to T)",
        subtitle="RidgeCV Bayesian Prior Shrinkage  |  Cross-Sector Indicators",
        bullets=[
            ("Remaining Window: ", "Unobserved future days (d+1 to month-end T)"),
            ("RidgeCV Regularization: ", "L2 penalty prevents multicollinearity from blowing up coefficients"),
            ("Explanatory Drivers: ", "Fuel price logistics spillover, USD/KHR exchange rate pass-through"),
            ("Calendar Kernel: ", "Exponential decay adjustments for major Khmer holidays (Pchum Ben, etc.)")
        ],
        title_bg=ROYAL_BLUE, body_bg='#EFF6FF', edge_color='#93C5FD'
    )

    # Arrows from Two Tiers to Blending
    ax.annotate('', xy=(42, 43), xytext=(26, 47), arrowprops=dict(arrowstyle='->', lw=2.0, color='#64748B'))
    ax.annotate('', xy=(58, 43), xytext=(74, 47), arrowprops=dict(arrowstyle='->', lw=2.0, color='#64748B'))

    # 4. Middle Card: Time-Weighted Horizon Blending
    draw_card(
        x=16, y=27, w=68, h=15,
        title="3. TIME-WEIGHTED HORIZON BLENDING ENGINE",
        subtitle="I_M(d) = ( d / T ) * Realized_Mean + ( (T - d) / T ) * Projected_Mean",
        bullets=[
            ("Dynamic Convergence: ", "On Day 1, projection acts as informative prior; by Day 30, index is 100% ground truth"),
            ("Monotonic Uncertainty Decay: ", "Forecast error envelope shrinks smoothly to zero as the full month is observed")
        ],
        title_bg='#334155', body_bg='#F8FAFC', edge_color='#CBD5E1'
    )

    # Arrows from Blending to Outputs
    ax.annotate('', xy=(28, 23), xytext=(38, 27), arrowprops=dict(arrowstyle='->', lw=2.0, color='#64748B'))
    ax.annotate('', xy=(72, 23), xytext=(62, 27), arrowprops=dict(arrowstyle='->', lw=2.0, color='#64748B'))

    # 5. Bottom Left: Official CSES Laspeyres Aggregation
    draw_card(
        x=4, y=3, w=44, h=19,
        title="AXIOMATIC LASPEYRES SYNTHESIS",
        subtitle="Official NIS / CSES 2020 Expenditure Weights",
        bullets=[
            ("Headline CPI: ", "Synthesized across all 12 UN COICOP divisions"),
            ("Weight Anchor: ", "Food (44.8%), Housing (17.1%), Transport (12.2%), Others (26.0%)"),
            ("Refined Core CPI: ", "Excludes volatile Food & Energy for underlying macro trend")
        ],
        title_bg=DARK_NAVY, body_bg='#F8FAFC', edge_color='#CBD5E1'
    )

    # 6. Bottom Right: Policy Early Warning & Output
    draw_card(
        x=52, y=3, w=44, h=19,
        title="POLICY EARLY WARNING & DECISION SUPPORT",
        subtitle="Published Daily  |  2 to 4 Weeks Ahead of Official NIS Releases",
        bullets=[
            ("Real-Time Nowcast: ", "Continuous daily inflation estimate available to MEF economists"),
            ("Benchmark Splicing: ", "Chain-linked to NIS 2006=100 base (conversion factor 2.19007)"),
            ("Metabase Dashboard: ", "Live interactive monitoring of price momentum and supply shocks")
        ],
        title_bg=TEAL, body_bg='#F0FDFA', edge_color='#5EEAD4'
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Flowchart successfully generated at: {output_path}")

if __name__ == "__main__":
    generate_flowchart("thesis/images/nowcasting_flowchart.png")
