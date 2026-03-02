"""
Product Cost Assumptions - View and edit per-SKU cost assumptions.
Fields: Inbound Freight, Warehouse Storage, Amazon FBA, Expected Product Life
Data source: CSV fallback, Azure SQL cache_cost_assumptions when connected.
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

from core.data_loader import load_cost_assumptions, load_product_directory
from core.ui_helpers import styled_header, styled_divider

styled_header("Product Cost Assumptions", "Per-SKU cost parameters: inbound freight, warehouse storage, Amazon FBA fees, and expected product life.")

# Load data
df = load_cost_assumptions()

if df.empty:
    st.warning("No cost assumption data found.")
    st.stop()

# Merge with product directory for Product Name and Reference SKU
dir_df = load_product_directory()
dir_info = dir_df[["SKU", "Product Name", "Reference SKU"]].drop_duplicates(subset="SKU") if "Product Name" in dir_df.columns and "Reference SKU" in dir_df.columns else dir_df[["SKU"]].drop_duplicates()
df = df.merge(dir_info, on="SKU", how="left")
# Reorder columns: SKU, Product Name, Reference SKU, then the rest
info_cols = ["SKU", "Product Name", "Reference SKU"]
other_cols = [c for c in df.columns if c not in info_cols]
df = df[[c for c in info_cols if c in df.columns] + other_cols]
df["Product Name"] = df["Product Name"].fillna("")
df["Reference SKU"] = df["Reference SKU"].fillna("")

# Search
search = st.text_input("Search SKU", placeholder="e.g. WYZECPAN", key="pc_search")
if search:
    df_display = df[df["SKU"].str.contains(search, case=False, na=False)]
else:
    df_display = df

# Format for display
formatted = df_display.copy()
for col in ["Inbound_Freight", "Warehouse_Storage", "Amazon_FBA"]:
    if col in formatted.columns:
        formatted[col] = formatted[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "-")
if "Expected_Product_Life" in formatted.columns:
    formatted["Expected_Product_Life"] = formatted["Expected_Product_Life"].apply(
        lambda x: f"{x:.0f} mo" if pd.notna(x) and x > 0 else "-"
    )

st.dataframe(formatted, use_container_width=True, hide_index=True, height=600)
st.caption(f"{len(df_display)} SKUs")

# DB editing section
styled_divider(label="Edit Cost Assumptions", icon="pencil-square")

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
    edit_sku = st.selectbox("SKU", sorted(df["SKU"].unique().tolist()), key="pc_edit_sku")

    # Get current values
    sku_row = df[df["SKU"] == edit_sku]
    current = {
        "Inbound_Freight": 0.0,
        "Warehouse_Storage": 0.0,
        "Amazon_FBA": 0.0,
        "Expected_Product_Life": 0.0,
    }
    if not sku_row.empty:
        row = sku_row.iloc[0]
        for k in current:
            val = row.get(k, 0)
            current[k] = float(val) if pd.notna(val) else 0.0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        new_inbound = st.number_input(
            "Inbound Freight ($)", value=current["Inbound_Freight"],
            min_value=0.0, step=0.1, format="%.2f", key="pc_inbound",
        )
    with col2:
        new_warehouse = st.number_input(
            "Warehouse Storage ($)", value=current["Warehouse_Storage"],
            min_value=0.0, step=0.1, format="%.2f", key="pc_warehouse",
        )
    with col3:
        new_fba = st.number_input(
            "Amazon FBA ($)", value=current["Amazon_FBA"],
            min_value=0.0, step=0.1, format="%.2f", key="pc_fba",
        )
    with col4:
        new_life = st.number_input(
            "Expected Life (months)", value=current["Expected_Product_Life"],
            min_value=0.0, step=1.0, format="%.0f", key="pc_life",
        )

    if st.button("Save Changes", key="pc_save"):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                MERGE cache_cost_assumptions AS target
                USING (SELECT ? AS sku) AS source
                ON target.sku = source.sku
                WHEN MATCHED THEN
                    UPDATE SET inbound_freight = ?, warehouse_storage = ?,
                               amazon_fba = ?, expected_product_life = ?,
                               synced_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (sku, inbound_freight, warehouse_storage, amazon_fba, expected_product_life)
                    VALUES (?, ?, ?, ?, ?);
            """, (edit_sku, new_inbound, new_warehouse, new_fba, new_life,
                  edit_sku, new_inbound, new_warehouse, new_fba, new_life))
            conn.commit()
            conn.close()
            st.success(f"Updated cost assumptions for {edit_sku}")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")
