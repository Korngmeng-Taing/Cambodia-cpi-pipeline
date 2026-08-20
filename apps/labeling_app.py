"""
apps/labeling_app.py
────────────────────
Streamlit Human-in-the-Loop Labeling & Triage Application for Cambodia CPI.

Features:
    1. Triage PENDING rows in silver.classification_queue.
    2. Manual Overrides: Assign division to product_key / barcode / SKU / name pattern.
    3. Category Map: Map store native category to COICOP division.
    4. Golden Test Set: Export labeled items directly into unit test suite.
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

# Add project root and dags to path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "orchestration", "dags"))

from pipeline.config import (  # noqa: E402
    COICOP_WEIGHTS,
    get_db_connection,
)

st.set_page_config(page_title="Cambodia CPI — Review & Labeling UI", layout="wide")

st.title("🇰🇭 Cambodia CPI — Classification Review Queue")
st.markdown("Human-in-the-loop triage for ambiguous and low-confidence product observations.")


def load_pending_queue() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        query = """
            SELECT id, product_key, store_slug, name_clean, category_native, price_khr, reason, created_at
            FROM silver.classification_queue
            WHERE status = 'PENDING'
            ORDER BY created_at DESC
            LIMIT 200;
        """
        df = pd.read_sql(query, conn)
        return df
    finally:
        conn.close()


def save_override(match_type: str, match_value: str, division: str, store_slug: str | None, queue_id: int, reason: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Insert into silver.coicop_override
            cur.execute("""
                INSERT INTO silver.coicop_override (match_type, match_value, store_slug, coicop_division, reason, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW());
            """, (match_type, match_value, store_slug or None, division, reason))

            # 2. Mark queue item as RESOLVED
            cur.execute("""
                UPDATE silver.classification_queue
                SET status = 'RESOLVED', resolved_division = %s, resolved_at = NOW()
                WHERE id = %s;
            """, (division, queue_id))
        conn.commit()
    finally:
        conn.close()


def save_category_map(store_slug: str, category_native: str, division: str, queue_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO silver.coicop_category_map (store_slug, category_native, coicop_division)
                VALUES (%s, %s, %s)
                ON CONFLICT (store_slug, category_native) DO UPDATE
                SET coicop_division = EXCLUDED.coicop_division;
            """, (store_slug, category_native, division))

            cur.execute("""
                UPDATE silver.classification_queue
                SET status = 'RESOLVED', resolved_division = %s, resolved_at = NOW()
                WHERE id = %s;
            """, (division, queue_id))
        conn.commit()
    finally:
        conn.close()


# Layout
df_queue = load_pending_queue()

st.sidebar.header("Queue Summary")
st.sidebar.metric("Pending Items", len(df_queue))

if df_queue.empty:
    st.success("🎉 Review queue is empty! All scraped items are classified.")
else:
    st.dataframe(
        df_queue[["id", "store_slug", "name_clean", "category_native", "price_khr", "reason"]],
        use_container_width=True,
    )

    st.subheader("Triage Selected Item")
    selected_id = st.selectbox("Select Queue ID to Review:", df_queue["id"].tolist())
    item = df_queue[df_queue["id"] == selected_id].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Store:** `{item['store_slug']}`")
        st.write(f"**Cleaned Name:** `{item['name_clean']}`")
        st.write(f"**Native Category:** `{item['category_native']}`")
        st.write(f"**Price (KHR):** `{item['price_khr']:,.2f} KHR`")

    with col2:
        division_options = [f"{code} — {meta['name']}" for code, meta in sorted(COICOP_WEIGHTS.items())]
        selected_div_str = st.selectbox("Target COICOP Division:", division_options)
        target_code = selected_div_str.split(" — ")[0]

        action = st.radio("Resolution Action:", ["Product Key Override", "Store Category Mapping", "Name Regex Rule"])

        if st.button("Apply Resolution", type="primary"):
            if action == "Product Key Override":
                save_override("product_key", item["product_key"], target_code, item["store_slug"], item["id"], "Manual Review UI")
                st.success(f"Assigned product {item['product_key']} -> Division {target_code}")
            elif action == "Store Category Mapping":
                save_category_map(item["store_slug"], str(item["category_native"]), target_code, item["id"])
                st.success(f"Mapped {item['store_slug']} category {item['category_native']} -> Division {target_code}")
            elif action == "Name Regex Rule":
                save_override("name", item["name_clean"], target_code, None, item["id"], "Name match from Review UI")
                st.success(f"Created name override for '{item['name_clean']}' -> Division {target_code}")

            st.rerun()
