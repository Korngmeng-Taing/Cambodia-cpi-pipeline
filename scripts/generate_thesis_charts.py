"""
scripts/generate_thesis_charts.py
─────────────────────────────────
Generates publication-quality charts and plots for the thesis and empirical research.
Outputs high-resolution 300-DPI PNGs to docs/figures/.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import psycopg2
import seaborn as sns

from pipeline.config import get_database_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("thesis_charts")

FIGURES_DIR = ROOT_DIR / "docs" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Publication styling
sns.set_theme(style="whitegrid", font="sans-serif")
plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "figure.dpi": 300,
})

def get_db_conn():
    conn_str = get_database_url().replace("postgresql+psycopg2://", "postgresql://", 1)
    conn_str = conn_str.replace("@postgres:", "@localhost:")
    return psycopg2.connect(conn_str)

def plot_figure1_headline_core(conn):
    """Figure 1: 39-Day Daily Headline and Core CPI Trajectory."""
    log.info("Generating Figure 1: Headline & Core CPI Trajectory...")
    query = """
        SELECT 
            d.calculation_date,
            MAX(d.headline_cpi) as headline_cpi,
            MAX(d.core_cpi) as core_cpi,
            MAX(CASE WHEN d.coicop_division = '01' THEN d.division_index END) as food_cpi,
            MAX(CASE WHEN d.coicop_division = '07' THEN d.division_index END) as transport_cpi,
            COALESCE(imp.imputation_rate_pct, 6.5) as imputation_rate_pct
        FROM gold.fct_cpi_daily d
        LEFT JOIN (
            SELECT calculation_date, 
                   ROUND(COUNT(CASE WHEN is_imputed THEN 1 END)::numeric / COUNT(*) * 100, 2) as imputation_rate_pct
            FROM gold.fct_elementary_indices
            GROUP BY calculation_date
        ) imp ON d.calculation_date = imp.calculation_date
        GROUP BY d.calculation_date, imp.imputation_rate_pct
        ORDER BY d.calculation_date;
    """
    df = pd.read_sql_query(query, conn)
    df["calculation_date"] = pd.to_datetime(df["calculation_date"])

    fig, ax1 = plt.subplots(figsize=(11, 5.5))

    ax1.axhline(100.0, color="gray", linestyle="--", linewidth=1.2, alpha=0.7, label="Base Period (July 2026 = 100)")
    ax1.plot(df["calculation_date"], df["headline_cpi"], color="#1f77b4", linewidth=2.2, label="Headline CPI (All Items)")
    ax1.plot(df["calculation_date"], df["core_cpi"], color="#2ca02c", linewidth=2.0, linestyle="-.", label="Core CPI (Excl. Food & Transport)")
    ax1.plot(df["calculation_date"], df["food_cpi"], color="#d62728", linewidth=1.8, linestyle=":", label="Food CPI (Div 01, Weight 44.78%)")

    ax1.set_ylabel("Index Level (July 2026 = 100)", fontweight="bold")
    ax1.set_title("Figure 1: High-Frequency Daily CPI Trajectory in Cambodia (Aug 18 – Sep 24, 2026)", fontweight="bold", pad=15)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    fig.autofmt_xdate()

    # Twin axis for imputation rate
    ax2 = ax1.twinx()
    ax2.fill_between(df["calculation_date"], 0, df["imputation_rate_pct"], color="#ff7f0e", alpha=0.15, label="Imputation Rate (%)")
    ax2.set_ylabel("Imputation Rate (%)", color="#d95f02", fontweight="bold")
    ax2.set_ylim(0, 40)
    ax2.grid(False)

    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower right", frameon=True, facecolor="white", framealpha=0.9)

    plt.tight_layout()
    out_path = FIGURES_DIR / "fig1_headline_core_trajectory.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    log.info(f"Saved: {out_path}")

def plot_figure2_5digit_food(conn):
    """Figure 2: 5-Digit Food Basket Dynamics (Rice, Pork, Fish, Dairy)."""
    log.info("Generating Figure 2: 5-Digit Food Dynamics...")
    query = """
        SELECT 
            calculation_date,
            coicop_code,
            category_name,
            jevons_index
        FROM gold.v_cpi_subclass_5digit_daily
        WHERE coicop_code IN ('01.1.1.1', '01.1.2.1', '01.1.3.1', '01.1.4.3', '01.2.2.2')
        ORDER BY calculation_date;
    """
    df = pd.read_sql_query(query, conn)
    df["calculation_date"] = pd.to_datetime(df["calculation_date"])

    palette = {
        "Rice": "#8c564b",
        "Fresh Pork": "#e377c2",
        "Fresh Fish": "#17becf",
        "Dairy Products": "#bcbd22",
        "Soft Drinks & Energy Drinks": "#7f7f7f"
    }

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.axhline(100.0, color="black", linestyle="--", linewidth=1.0, alpha=0.6)

    for cat_name, group in df.groupby("category_name"):
        color = palette.get(cat_name, "#333333")
        ax.plot(group["calculation_date"], group["jevons_index"], label=f"{cat_name}", linewidth=2.0, color=color)

    ax.set_ylabel("Subclass Elementary Jevons Index (Jul 2026 = 100)", fontweight="bold")
    ax.set_title("Figure 2: UN COICOP 2018 5-Digit Subclass Dynamics in Cambodia (Daily)", fontweight="bold", pad=15)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    fig.autofmt_xdate()
    ax.legend(title="5-Digit COICOP Subclass", loc="upper left", frameon=True, facecolor="white", framealpha=0.9)

    plt.tight_layout()
    out_path = FIGURES_DIR / "fig2_5digit_food_dynamics.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    log.info(f"Saved: {out_path}")

def plot_figure3_rice_daily(conn):
    """Figure 3: High-Frequency Rice Inflation & Item Count."""
    log.info("Generating Figure 3: Rice Daily Price Series...")
    query = """
        SELECT 
            calculation_date,
            distinct_rice_products,
            avg_current_price_khr,
            rice_cpi_jevons,
            inflation_rate_pct
        FROM gold.v_cpi_rice_daily
        ORDER BY calculation_date;
    """
    df = pd.read_sql_query(query, conn)
    df["calculation_date"] = pd.to_datetime(df["calculation_date"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})

    # Upper panel: Rice Jevons Index & Avg Price KHR
    ax1.plot(df["calculation_date"], df["rice_cpi_jevons"], color="#8c564b", linewidth=2.4, label="Rice Jevons Index (COICOP 01.1.1.1)")
    ax1.axhline(100.0, color="gray", linestyle="--", linewidth=1.0)
    ax1.set_ylabel("Rice Price Index (July = 100)", fontweight="bold", color="#8c564b")
    ax1.set_title("Figure 3: Daily Rice Inflation Index & High-Frequency Basket Density in Phnom Penh", fontweight="bold", pad=12)

    ax1_twin = ax1.twinx()
    ax1_twin.plot(df["calculation_date"], df["avg_current_price_khr"] / 1000, color="#1f77b4", linestyle=":", linewidth=1.8, label="Average Price (1,000 KHR / Unit)")
    ax1_twin.set_ylabel("Mean Price (kKHR)", color="#1f77b4", fontweight="bold")
    ax1_twin.grid(False)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1_twin.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower left", frameon=True, facecolor="white")

    # Lower panel: Monitored Rice Product Varieties
    ax2.bar(df["calculation_date"], df["distinct_rice_products"], color="#2ca02c", alpha=0.7, width=0.8, label="Tracked Rice Products (SKUs)")
    ax2.set_ylabel("Product Count", fontweight="bold")
    ax2.set_ylim(200, 280)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    ax2.legend(loc="upper right", frameon=True, facecolor="white")

    fig.autofmt_xdate()
    plt.tight_layout()
    out_path = FIGURES_DIR / "fig3_rice_daily_tracker.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    log.info(f"Saved: {out_path}")

def plot_figure4_division_distribution(conn):
    """Figure 4: 12-Division Expenditure Weights vs Canonical Item Coverage."""
    log.info("Generating Figure 4: 12-Division Weights & Coverage...")
    query = """
        SELECT 
            coicop_division,
            COUNT(*) as item_count
        FROM silver.canonical_items
        GROUP BY coicop_division;
    """
    df_items = pd.read_sql_query(query, conn)
    item_map = dict(zip(df_items["coicop_division"], df_items["item_count"]))

    divisions = [
        ("01", "Food & Non-Alcoholic Bev", 44.775),
        ("02", "Alcoholic Bev & Tobacco", 1.625),
        ("03", "Clothing & Footwear", 3.036),
        ("04", "Housing & Utilities", 17.084),
        ("05", "Furnishings & Maint.", 2.743),
        ("06", "Health", 5.141),
        ("07", "Transport", 12.228),
        ("08", "Communication", 1.136),
        ("09", "Recreation & Culture", 2.912),
        ("10", "Education", 1.174),
        ("11", "Restaurants & Hotels", 5.861),
        ("12", "Misc. Goods & Services", 2.285),
    ]

    div_labels = [f"Div {d[0]}: {d[1]}" for d in divisions]
    weights = [d[2] for d in divisions]
    item_counts = [item_map.get(d[0], 0) for d in divisions]

    y = np.arange(len(divisions))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6.5), sharey=True)

    # Panel 1: NIS Expenditure Weights
    bars1 = ax1.barh(y, weights, color="#1f77b4", edgecolor="none", height=0.65)
    ax1.set_xlabel("Official NIS Expenditure Weight (%)", fontweight="bold")
    ax1.set_yticks(y)
    ax1.set_yticklabels(div_labels)
    ax1.invert_yaxis()
    for bar in bars1:
        w = bar.get_width()
        ax1.text(w + 0.5, bar.get_y() + bar.get_height()/2, f"{w:.2f}%", va="center", fontsize=9)
    ax1.set_title("NIS Expenditure Weight ($W_d$)", fontweight="bold")

    # Panel 2: Canonical Items Scraped
    bars2 = ax2.barh(y, item_counts, color="#2ca02c", edgecolor="none", height=0.65)
    ax2.set_xlabel("Number of Scraped Canonical Products", fontweight="bold")
    for bar in bars2:
        w = bar.get_width()
        ax2.text(w + 200, bar.get_y() + bar.get_height()/2, f"{int(w):,}", va="center", fontsize=9)
    ax2.set_title("Product Density in Pipeline ($N_d$)", fontweight="bold")

    fig.suptitle("Figure 4: Cambodia CPI Official Weights vs. Web-Scraped Product Coverage", fontweight="bold", y=0.98)
    plt.tight_layout()
    out_path = FIGURES_DIR / "fig4_division_weights_coverage.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    log.info(f"Saved: {out_path}")

def plot_figure5_store_balanced_ablation(conn):
    """Figure 5: Store-Balanced Jevons vs Flat Jevons (Delishop Dominance Mitigation)."""
    log.info("Generating Figure 5: Store-Balanced vs Flat Jevons Ablation...")
    query = """
        SELECT 
            sub.calculation_date,
            MAX(d.headline_cpi) as balanced_cpi,
            -- Reconstructing flat Jevons unweighted across all items
            ROUND(EXP(AVG(LN(sub.price_ratio)))::numeric * 100, 4) as flat_cpi
        FROM (
            SELECT calculation_date, price_ratio 
            FROM gold.fct_elementary_indices
            WHERE price_ratio > 0
        ) sub
        JOIN (SELECT DISTINCT calculation_date, headline_cpi FROM gold.fct_cpi_daily) d 
          ON sub.calculation_date = d.calculation_date
        GROUP BY sub.calculation_date
        ORDER BY sub.calculation_date;
    """
    df = pd.read_sql_query(query, conn)
    df["calculation_date"] = pd.to_datetime(df["calculation_date"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})

    ax1.plot(df["calculation_date"], df["balanced_cpi"], color="#1f77b4", linewidth=2.2, label="Two-Stage Store-Balanced Jevons (Production)")
    ax1.plot(df["calculation_date"], df["flat_cpi"], color="#d62728", linestyle="--", linewidth=1.8, label="Flat Jevons (Unbalanced, Catalog-Size Biased)")
    ax1.axhline(100.0, color="gray", linestyle=":", alpha=0.7, label="NIS Official Benchmark (100.00)")
    ax1.set_ylabel("Index Level (Jul 2026 = 100)", fontweight="bold")
    ax1.set_title("Figure 5: Ablation Analysis — Store-Balanced vs. Unweighted Flat Jevons Aggregation", fontweight="bold", pad=12)
    ax1.legend(loc="upper left", frameon=True, facecolor="white")

    # Lower panel: Index Divergence Spread (Spread = Flat - Balanced)
    spread = df["flat_cpi"] - df["balanced_cpi"]
    ax2.plot(df["calculation_date"], spread, color="#9467bd", linewidth=1.8, label="Divergence Spread (Flat - Balanced)")
    ax2.axhline(0.0, color="black", linestyle="-", linewidth=0.8, alpha=0.5)
    ax2.fill_between(df["calculation_date"], 0, spread, color="#9467bd", alpha=0.2)
    ax2.set_ylabel("Divergence (pts)", fontweight="bold")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    ax2.legend(loc="upper right", frameon=True, facecolor="white")

    fig.autofmt_xdate()
    plt.tight_layout()
    out_path = FIGURES_DIR / "fig5_store_balancing_ablation.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    log.info(f"Saved: {out_path}")

def main():
    log.info("Connecting to database for thesis visualizations...")
    conn = get_db_conn()
    try:
        plot_figure1_headline_core(conn)
        plot_figure2_5digit_food(conn)
        plot_figure3_rice_daily(conn)
        plot_figure4_division_distribution(conn)
        plot_figure5_store_balanced_ablation(conn)
        log.info("🎉 All 5 publication charts successfully generated in docs/figures/!")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
