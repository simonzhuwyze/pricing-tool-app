"""
Outbound Shipping - View and edit per-SKU per-channel outbound shipping costs.
Data source: Azure SQL cache_outbound_shipping table.
"""

import os
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip().strip('"').strip("'")

from core.ui_helpers import styled_header, styled_divider
from core.auth import require_permission

styled_header("Outbound Shipping", "Outbound shipping costs per SKU per channel. Values in USD per unit.")
require_permission("edit_assumptions", "Outbound Shipping")

# Load data from Azure SQL
try:
    from core.database import get_connection, get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()

    db_df = pd.read_sql_table("cache_outbound_shipping", engine)
    # Normalize columns
    col_map = {}
    for c in db_df.columns:
        cl = c.lower()
        if cl == "sku":
            col_map[c] = "SKU"
        elif cl == "channel":
            col_map[c] = "Channel"
        elif "shipping" in cl or "outbound" in cl:
            col_map[c] = "Outbound_Shipping_Cost"
    df = db_df.rename(columns=col_map)

    dir_df = pd.read_sql_table("cache_product_directory", engine)
    dir_df = dir_df.rename(columns={"sku": "SKU", "product_name": "Product Name", "reference_sku": "Reference SKU"})
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()

if df.empty:
    st.warning("No outbound shipping data found. Run CSV Sync from DB Admin page.")
    st.stop()

# Pivot for display: SKU x Channel
pivot = df.pivot_table(index="SKU", columns="Channel", values="Outbound_Shipping_Cost")

# Product Name and Reference SKU
sku_to_name = dict(zip(dir_df["SKU"], dir_df.get("Product Name", pd.Series(dtype=str))))
sku_to_ref = dict(zip(dir_df["SKU"], dir_df.get("Reference SKU", pd.Series(dtype=str))))

# Search
search = st.text_input("Search SKU", placeholder="e.g. WYZECPAN", key="ob_search")
if search:
    pivot = pivot[pivot.index.str.contains(search, case=False, na=False)]

# Add Product Name and Reference SKU columns
pivot = pivot.reset_index()
pivot.insert(1, "Product Name", pivot["SKU"].map(sku_to_name).fillna(""))
pivot.insert(2, "Reference SKU", pivot["SKU"].map(sku_to_ref).fillna(""))

# Format as dollar for display (only data columns, not info columns)
data_cols = [c for c in pivot.columns if c not in ("SKU", "Product Name", "Reference SKU")]
formatted = pivot.style.format({c: "${:.2f}" for c in data_cols}, na_rep="-")

st.dataframe(formatted, use_container_width=True, hide_index=True, height=600)
st.caption(f"{len(pivot)} SKUs x {len(data_cols)} channels")

# DB editing section
styled_divider(label="Edit Single Value", icon="pencil-square")
st.caption("Update a specific SKU/Channel outbound shipping cost. Saves to Azure SQL cache.")

db_connected = False
try:
    pd.read_sql("SELECT 1", engine)
    db_connected = True
except Exception:
    pass

if not db_connected:
    st.info("Connect to Azure SQL via DB Admin to enable editing.")
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        edit_sku = st.selectbox("SKU", sorted(pivot["SKU"].tolist()), key="ob_edit_sku")
    with col2:
        edit_channel = st.selectbox("Channel", sorted(data_cols), key="ob_edit_ch")
    with col3:
        sku_mask = pivot["SKU"] == edit_sku
        current_val = pivot.loc[sku_mask, edit_channel].values[0] if sku_mask.any() and edit_channel in pivot.columns else 0
        if pd.isna(current_val):
            current_val = 0.0
        new_val = st.number_input(
            "New Cost ($)",
            value=float(current_val),
            min_value=0.0, max_value=999.0, step=0.1, format="%.2f",
            key="ob_new_val",
        )

    if st.button("Save Change", key="ob_save"):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                MERGE cache_outbound_shipping AS target
                USING (SELECT ? AS sku, ? AS channel) AS source
                ON target.sku = source.sku AND target.channel = source.channel
                WHEN MATCHED THEN
                    UPDATE SET outbound_shipping_cost = ?, synced_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (sku, channel, outbound_shipping_cost) VALUES (?, ?, ?);
            """, (edit_sku, edit_channel, new_val, edit_sku, edit_channel, new_val))
            conn.commit()
            conn.close()
            st.success(f"Updated {edit_sku} / {edit_channel} = ${new_val:.2f}")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")
