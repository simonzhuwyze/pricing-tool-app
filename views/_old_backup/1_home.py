"""
Home Page - Product Selector + Basic Inputs
Replicates the Power BI Home Page functionality.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.data_loader import load_product_directory, load_sku_mapping, CHANNELS
from core.cpam_engine import (
    UserInputs, ProductInfo, ChannelAssumptions, StaticAssumptions,
    CPAMBreakdown, calculate_channel_cpam, calculate_weighted_cpam,
)

st.title("Pricing Tool")
st.caption("Product Selection & Quick CPAM Summary")

# Load data
products = load_product_directory()
sku_mapping = load_sku_mapping()

# --- Product Selector ---
col1, col2 = st.columns([2, 3])
with col1:
    # Create display labels: SKU - Product Name
    products["label"] = products["SKU"] + " - " + products["Product Name"].fillna("")
    selected_label = st.selectbox(
        "Select Product",
        options=products["label"].tolist(),
        index=0,
        key="product_selector",
    )
    selected_sku = products[products["label"] == selected_label]["SKU"].iloc[0]
    st.session_state.selected_sku = selected_sku

with col2:
    product_row = products[products["SKU"] == selected_sku].iloc[0]
    st.markdown(f"**SKU:** `{selected_sku}`")
    ref_sku = product_row.get("Reference SKU", "")
    if pd.notna(ref_sku) and ref_sku:
        st.markdown(f"**Reference SKU:** `{ref_sku}`")

# --- Basic Inputs ---
st.divider()
st.subheader("Key Inputs")

product_row = products[products["SKU"] == selected_sku].iloc[0]
default_msrp = float(product_row.get("Default MSRP", 0) or 0)
default_fob = float(product_row.get("Default FOB", 0) or 0)
default_tariff = float(product_row.get("Default Tariff Rate", 0) or 0) * 100  # Convert to %

col_msrp, col_fob, col_tariff, col_promo = st.columns(4)

with col_msrp:
    msrp = st.number_input(
        "MSRP ($)",
        value=default_msrp,
        min_value=0.0,
        step=0.01,
        format="%.2f",
        key="input_msrp",
    )

with col_fob:
    fob = st.number_input(
        "FOB ($)",
        value=default_fob,
        min_value=0.0,
        step=0.01,
        format="%.2f",
        key="input_fob",
    )

with col_tariff:
    tariff = st.number_input(
        "Tariff Rate (%)",
        value=default_tariff,
        min_value=0.0,
        max_value=200.0,
        step=0.25,
        format="%.2f",
        key="input_tariff",
    )

with col_promo:
    promo_mix = st.number_input(
        "Promotion Mix (%)",
        value=0.0,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        format="%.0f",
        key="input_promo_mix",
        help="Percentage of units sold under promotion (e.g., 15 = 15%)",
    )

# Save to session state
st.session_state.user_inputs = {
    "msrp": msrp,
    "fob": fob,
    "tariff_rate": tariff,
    "promotion_mix": promo_mix,
}

# --- Reference Values Toggle ---
with st.expander("Reference Values (from Product Directory)"):
    ref_cols = st.columns(3)
    with ref_cols[0]:
        st.metric("Default MSRP", f"${default_msrp:.2f}")
    with ref_cols[1]:
        st.metric("Default FOB", f"${default_fob:.2f}")
    with ref_cols[2]:
        st.metric("Default Tariff Rate", f"{default_tariff:.1f}%")

# --- Quick CPAM Summary ---
st.divider()
st.subheader("CPAM Summary")

# Look up product group for special rules
sku_info = sku_mapping[sku_mapping["SKU"] == selected_sku]
if sku_info.empty and pd.notna(ref_sku) and ref_sku:
    sku_info = sku_mapping[sku_mapping["SKU"] == ref_sku]

product_group = sku_info["Product_Group"].iloc[0] if not sku_info.empty and "Product_Group" in sku_info.columns else ""
product_line = sku_info["Product_Line"].iloc[0] if not sku_info.empty and "Product_Line" in sku_info.columns else ""

product = ProductInfo(
    sku=selected_sku,
    product_name=str(product_row.get("Product Name", "")),
    product_group=str(product_group) if pd.notna(product_group) else "",
    product_line=str(product_line) if pd.notna(product_line) else "",
    reference_sku=str(ref_sku) if pd.notna(ref_sku) else "",
)

static = StaticAssumptions(
    uid_cam=0.10,
    royalties_cam=0.20,
    royalties_bulb_rate=0.05,
    monthly_cloud_cost_cam=0.08,
    monthly_cloud_cost_noncam=0.0,
    eos_rate=0.01,
)

user_inputs = UserInputs(
    msrp=msrp,
    fob=fob,
    tariff_rate=tariff,
    promotion_mix=promo_mix,
)

# Load assumptions for each channel and calculate
from core.data_loader import load_po_discount, load_outbound_shipping

po_discount_df = load_po_discount()
outbound_df = load_outbound_shipping()

channel_results = []
channel_mix_values = st.session_state.get("channel_mix", {})

for ch in CHANNELS:
    # Get PO discount rate for this SKU/channel
    po_row = po_discount_df[
        (po_discount_df["SKU"] == selected_sku) & (po_discount_df["Channel"] == ch)
    ]
    po_rate = float(po_row["PO_Discount_Rate"].iloc[0]) if not po_row.empty else 0.0

    # Get outbound shipping
    ob_row = outbound_df[
        (outbound_df["SKU"] == selected_sku) & (outbound_df["Channel"] == ch)
    ]
    ob_cost = float(ob_row["Outbound_Shipping_Cost"].iloc[0]) if not ob_row.empty else 0.0

    mix_val = channel_mix_values.get(ch, 0.0) / 100.0  # Convert from % to decimal

    assumptions = ChannelAssumptions(
        channel=ch,
        po_discount_rate=po_rate,
        outbound_shipping=ob_cost,
        channel_mix=mix_val,
        customer_service_rate=0.03,  # Default 3%
        cc_fee_rate=0.03,            # Default 3%
        marketing_rate=0.03,         # Default 3%
    )

    result = calculate_channel_cpam(user_inputs, product, assumptions, static)
    channel_results.append(result)

# Build summary table (similar to CPAM Summary in Power BI)
summary_data = []
for r in channel_results:
    summary_data.append({
        "Channel": r.channel,
        "CPAM $ (Promo)": r.cpam_dollar,
        "CPAM % (Promo)": r.cpam_pct,
        "CPAM $ (Full)": r.cpam_dollar_full,
        "CPAM % (Full)": r.cpam_pct_full,
        "CPAM $ (Blended)": r.cpam_dollar_blended,
        "CPAM % (Blended)": r.cpam_pct_blended,
        "Net Revenue": r.net_revenue,
    })

# Add weighted average row
weighted = calculate_weighted_cpam(channel_results)
if weighted:
    summary_data.append({
        "Channel": "Weighted Avg",
        "CPAM $ (Promo)": weighted.cpam_dollar,
        "CPAM % (Promo)": weighted.cpam_pct,
        "CPAM $ (Full)": weighted.cpam_dollar_full,
        "CPAM % (Full)": weighted.cpam_pct_full,
        "CPAM $ (Blended)": weighted.cpam_dollar_blended,
        "CPAM % (Blended)": weighted.cpam_pct_blended,
        "Net Revenue": weighted.net_revenue,
    })

summary_df = pd.DataFrame(summary_data)

# Format and display
st.dataframe(
    summary_df.style.format({
        "CPAM $ (Promo)": "${:.2f}",
        "CPAM % (Promo)": "{:.1%}",
        "CPAM $ (Full)": "${:.2f}",
        "CPAM % (Full)": "{:.1%}",
        "CPAM $ (Blended)": "${:.2f}",
        "CPAM % (Blended)": "{:.1%}",
        "Net Revenue": "${:.2f}",
    }),
    use_container_width=True,
    hide_index=True,
)

st.info(
    "Set Channel Mix on the **Channel Mix** page to see weighted averages. "
    "View the full CPAM breakdown on the **CPAM Calculator** page."
)
