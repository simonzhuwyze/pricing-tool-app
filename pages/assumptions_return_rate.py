"""
Return Rate - View and edit per-SKU per-channel return rates.
Data source: CSV fallback, Azure SQL cache_return_rate_sku when connected.
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

from core.data_loader import load_return_rate_by_sku, load_product_directory
from core.ui_helpers import styled_header, styled_divider, styled_metric_cards
from core.auth import require_permission

styled_header("Return Rate", "Return rates per SKU per channel. Values are decimals (0.05 = 5% return rate).")
require_permission("edit_assumptions", "Return Rate")

# Load data
df = load_return_rate_by_sku()

if df.empty:
    st.warning("No return rate data found.")
    st.stop()

# Pivot for display: SKU x Channel
pivot = df.pivot_table(index="SKU", columns="Channel", values="Return_Rate")

# Load product directory for Product Name and Reference SKU
dir_df = load_product_directory()
sku_to_name = dict(zip(dir_df["SKU"], dir_df.get("Product Name", pd.Series(dtype=str))))
sku_to_ref = dict(zip(dir_df["SKU"], dir_df.get("Reference SKU", pd.Series(dtype=str))))

# Search
search = st.text_input("Search SKU", placeholder="e.g. WYZECPAN", key="rr_search")
if search:
    pivot = pivot[pivot.index.str.contains(search, case=False, na=False)]

# Add Product Name and Reference SKU columns
pivot = pivot.reset_index()
pivot.insert(1, "Product Name", pivot["SKU"].map(sku_to_name).fillna(""))
pivot.insert(2, "Reference SKU", pivot["SKU"].map(sku_to_ref).fillna(""))

# Format percentages for display (only data columns, not info columns)
data_cols = [c for c in pivot.columns if c not in ("SKU", "Product Name", "Reference SKU")]
formatted = pivot.style.format({c: "{:.2%}" for c in data_cols}, na_rep="-")

st.dataframe(formatted, use_container_width=True, hide_index=True, height=600)
st.caption(f"{len(pivot)} SKUs x {len(data_cols)} channels")

# Summary stats
styled_divider(label="Summary Statistics", icon="graph-up")
col1, col2, col3 = st.columns(3)
with col1:
    avg_rate = df["Return_Rate"].mean()
    st.metric("Average Return Rate", f"{avg_rate:.2%}")
with col2:
    max_rate = df["Return_Rate"].max()
    max_row = df.loc[df["Return_Rate"].idxmax()]
    st.metric("Highest Return Rate", f"{max_rate:.2%}", help=f"{max_row['SKU']} / {max_row['Channel']}")
with col3:
    st.metric("Total Data Points", f"{len(df)}")
styled_metric_cards()

# DB editing section
styled_divider(label="Edit Single Value", icon="pencil-square")

db_connected = False
try:
    from core.database import get_connection, get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    pd.read_sql("SELECT 1", engine)
    db_connected = True
except Exception:
    pass

if not db_connected:
    st.info("Connect to Azure SQL via DB Admin to enable editing.")
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        edit_sku = st.selectbox("SKU", sorted(pivot["SKU"].tolist()), key="rr_edit_sku")
    with col2:
        edit_channel = st.selectbox("Channel", sorted(data_cols), key="rr_edit_ch")
    with col3:
        sku_mask = pivot["SKU"] == edit_sku
        current_val = pivot.loc[sku_mask, edit_channel].values[0] if sku_mask.any() and edit_channel in pivot.columns else 0
        if pd.isna(current_val):
            current_val = 0.0
        new_val = st.number_input(
            "New Rate (decimal)",
            value=float(current_val),
            min_value=0.0, max_value=1.0, step=0.001, format="%.4f",
            key="rr_new_val",
        )

    if st.button("Save Change", key="rr_save"):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                MERGE cache_return_rate_sku AS target
                USING (SELECT ? AS sku, ? AS channel) AS source
                ON target.sku = source.sku AND target.channel = source.channel
                WHEN MATCHED THEN
                    UPDATE SET return_rate = ?, synced_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (sku, channel, return_rate) VALUES (?, ?, ?);
            """, (edit_sku, edit_channel, new_val, edit_sku, edit_channel, new_val))
            conn.commit()
            conn.close()
            st.success(f"Updated {edit_sku} / {edit_channel} = {new_val:.4f}")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")
